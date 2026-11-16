import asyncio
import json
import os
import time
from pathlib import Path

import agents
import llm
from agent_team import run_team, to_speak_event
from data_sources.health import update_health as ds_update_health
from mcp_client import MCPClient
from weather import fetch_context, demo_context
from pv_model import compute_metrics

MCP_ENABLED = os.getenv("MCP_ENABLED", "1") == "1"

CONFIG_PATH = Path(__file__).parent / "data" / "pv_config.json"

AGENT_INPUT_KEYS = {
    "weather": ["weather", "decision"],
    "soiling": ["soiling"],
    "economics": ["economics", "decision"],
    "ops": ["decision", "weather", "economics", "soiling"],
}


def load_config(overrides: dict | None = None) -> dict:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    overrides = overrides or {}
    for key in ("capacity_mw", "days_since_clean", "price_per_kwh", "cleaning_cost"):
        value = overrides.get(key)
        if value is None:
            continue
        if key == "capacity_mw":
            config["site"]["capacity_mw"] = float(value)
        elif key == "days_since_clean":
            config["site"]["days_since_clean"] = int(value)
        elif key == "price_per_kwh":
            config["economics"]["price_per_kwh"] = float(value)
        elif key == "cleaning_cost":
            config["economics"]["cleaning_cost"] = float(value)
    config["scenario"] = overrides.get("scenario", "demo")
    return config


def envelope(kind: str, **payload) -> dict:
    return {"type": kind, "ts": round(time.time(), 3), **payload}


def _agent_input_event(agent: str, metrics: dict) -> dict:
    keys = AGENT_INPUT_KEYS.get(agent, [])
    return envelope("agent_input", agent=agent, input={k: metrics.get(k) for k in keys})


async def stream_decision(overrides: dict | None = None):
    config = load_config(overrides)
    yield envelope(
        "session_start",
        site=config["site"],
        economics=config["economics"],
        agents=[{"id": k, **v} for k, v in agents.AGENT_META.items() if k not in ("critic", "arbiter")],
        mode=llm.mode(),
    )

    mcp = None
    if MCP_ENABLED:
        try:
            mcp = MCPClient()
            init = await asyncio.to_thread(mcp.initialize)
            tools = await asyncio.to_thread(mcp.list_tools)
            yield envelope(
                "mcp_ready",
                server=(init.get("serverInfo") or {}).get("name"),
                protocol=init.get("protocolVersion"),
                tools=[t["name"] for t in tools],
            )
        except Exception as e:
            mcp = None
            yield envelope("mcp_error", message=f"{type(e).__name__}: {e}")

    try:
        if mcp:
            t0 = time.time()
            context = await asyncio.to_thread(
                mcp.call_tool,
                "get_site_data",
                {
                    "lat": config["site"]["lat"],
                    "lng": config["site"]["lng"],
                    "loss_pct": config["economics"].get("pvgis_loss_pct", 10.0),
                    "mode": config.get("scenario", "demo"),
                },
            )
            for r in context.get("data_source_records", []):
                ds_update_health(
                    r["source"],
                    status="ok" if r.get("status") in ("ok", "cached") else "error",
                    error=r.get("error_message"),
                    data_kind=r.get("data_kind"),
                    is_cached=r.get("is_cached", False),
                )
            yield envelope(
                "mcp_tool_call",
                tool="get_site_data",
                ok=True,
                elapsed_ms=round((time.time() - t0) * 1000, 1),
            )
        else:
            context = demo_context() if config.get("scenario") == "demo" else await fetch_context(
                config["site"]["lat"],
                config["site"]["lng"],
                loss_pct=config["economics"].get("pvgis_loss_pct", 10.0),
            )

        if mcp:
            t0 = time.time()
            metrics = await asyncio.to_thread(
                mcp.call_tool, "calc_economics", {"config": config, "context": context}
            )
            yield envelope(
                "mcp_tool_call",
                tool="calc_economics",
                ok=True,
                elapsed_ms=round((time.time() - t0) * 1000, 1),
            )
        else:
            metrics = compute_metrics(config, context)
    finally:
        if mcp:
            await asyncio.to_thread(mcp.close)
            mcp = None

    yield envelope(
        "data_loaded",
        weather=metrics["weather"],
        air=metrics["soiling"],
        data_quality=metrics["data_quality"],
    )
    yield envelope("decision_snapshot", metrics=metrics)
    await asyncio.sleep(0.4)

    # V3.0-5：七个 Agent 真实执行（含 Critic 与 Decision），LLM 仅增强 Critic 且失败自动跳过
    team = await run_team(metrics, config)
    metrics = team["metrics"]
    yield envelope("round_start", round=1)
    for res in team["agent_results"]:
        yield envelope(
            "agent_result",
            agent=res["agent_name"],
            result={
                "agent_name": res["agent_name"],
                "status": res["status"],
                "conclusion": res["conclusion"],
                "evidence": res["evidence"],
                "data_sources": res["data_sources"],
                "assumptions": res["assumptions"],
                "uncertainties": res["uncertainties"],
                "recommendation": res["recommendation"],
                "confidence_type": res["confidence_type"],
                "confidence": res.get("confidence"),
                "veto_type": res.get("veto_type"),
            },
        )
        yield to_speak_event(res)
        await asyncio.sleep(0.35)

    if team["critic_issues"]:
        yield envelope("critic_issues", issues=team["critic_issues"])
    yield envelope(
        "agent_decision",
        final_action=team["final_action"],
        veto_applied=team["veto_applied"],
        llm_enhanced=team["llm_enhanced"],
        decision_trace=team["decision_trace"],
    )

    if metrics["decision"]["action"] == "insufficient_data":
        yield envelope("round_start", round=1)
        yield agents.speak(
            "critic",
            "object",
            f"数据不足，无法启动协商：{metrics['decision']['reason']}",
            refs=metrics["decision"].get("data_insufficient", []),
            confidence=0.95,
        )
        yield envelope(
            "final",
            metrics=metrics,
            forced=False,
            mode=llm.mode(),
            summary="数据不足，暂时无法判断；请检查数据源状态后重试。",
        )
        return

    # 第二轮：旧协商层（可视化 + 仲裁）。若 Safety Agent 已否决，直接输出否决结论，不再进入仲裁。
    forced = False
    safety_result = next((r for r in team["agent_results"] if r["agent_name"] == "safety"), None)
    if safety_result and safety_result.get("recommendation") == "veto":
        yield envelope("round_start", round=2)
        yield agents.speak(
            "critic",
            "support",
            f"安全否决生效（{safety_result.get('veto_type')}），最终决策 {team['final_action']}；"
            "安全约束优先级高于经济收益，不进入经济仲裁。",
            refs=["safety_veto"],
            confidence=0.95,
        )
        await asyncio.sleep(0.3)
    else:
        opinions: list[dict] = []
        yield envelope("round_start", round=2)
        for fn, agent_id in (
            (agents.weather_opinion, "weather"),
            (agents.soiling_opinion, "soiling"),
            (agents.economics_opinion, "economics"),
            (agents.ops_opinion, "ops"),
        ):
            yield _agent_input_event(agent_id, metrics)
            event = fn(metrics, config)
            opinions.append(event)
            yield event
            await asyncio.sleep(0.45)

        passed, critic_evt = agents.critic_judge(metrics, opinions)
        yield critic_evt
        await asyncio.sleep(0.35)

        if not passed and metrics["decision"].get("interval_block"):
            passed = True
            yield agents.speak(
                "critic",
                "support",
                f"距上次清洗不足最小间隔（{metrics['decision']['min_clean_interval_days']} 天），设备与成本约束优先，维持暂不清洗；建议间隔满足后再评估。",
                refs=[f"最小间隔 {metrics['decision']['min_clean_interval_days']} 天"],
                confidence=0.9,
            )
            await asyncio.sleep(0.3)

        if not passed:
            blockers = {o["agent"] for o in opinions if o["stance"] == "object"}
            if "weather" in blockers:
                metrics = agents.defer_plan(metrics, config)
            elif "economics" in blockers or "soiling" in blockers:
                arb_evt = agents.arbitrate(metrics, config)
                yield arb_evt
                await asyncio.sleep(0.4)
                metrics = agents.apply_partial(metrics, config)
            yield envelope("decision_snapshot", metrics=metrics)
            yield envelope("round_start", round=3)
            await asyncio.sleep(0.3)

            opinions2 = []
            if metrics["decision"]["action"] == "defer":
                yield _agent_input_event("ops", metrics)
                op = agents.ops_opinion(metrics, config)
                opinions2.append(op)
                yield op
                await asyncio.sleep(0.4)
                passed, critic_evt = agents.critic_defer_review(metrics, config)
                yield critic_evt
                forced = not passed
            else:
                for fn, agent_id in (
                    (agents.weather_opinion, "weather"),
                    (agents.economics_opinion, "economics"),
                    (agents.ops_opinion, "ops"),
                ):
                    yield _agent_input_event(agent_id, metrics)
                    event = fn(metrics, config)
                    opinions2.append(event)
                    yield event
                    await asyncio.sleep(0.4)
                passed, critic_evt = agents.critic_judge(metrics, opinions2)
                yield critic_evt
                forced = not passed
            await asyncio.sleep(0.3)

    if metrics.get("agent_execution"):
        metrics["agent_execution"]["final_action"] = metrics["decision"]["action"]

    summary = await llm.chat(
        "你是光伏电站运维决策助手，用不超过100字总结本次清洗决策的关键依据，语气专业克制。",
        f"决策：{metrics['decision']}\n收益：{metrics['economics']}\n气象：{metrics['weather']}",
    )
    yield envelope(
        "final",
        metrics=metrics,
        forced=forced,
        mode=llm.mode(),
        summary=summary
        or f"{metrics['decision']['reason']}；收益为估算模型，执行前请结合现场检测复核。",
    )