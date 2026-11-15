import asyncio
import json
import os
import time
from pathlib import Path

import agents
import llm
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

    opinions: list[dict] = []
    yield envelope("round_start", round=1)
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

    forced = False
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
        yield envelope("round_start", round=2)
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