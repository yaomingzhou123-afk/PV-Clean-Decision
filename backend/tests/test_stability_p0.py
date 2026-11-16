"""批次 1（P0-1/P0-4/P0-5/P0-7）：数据真实性与决策流程一致性修复的回归测试。

对应 Bug：
- P0-1 数据不足时仍执行七 Agent，输出 "None" 和"具备作业窗口"
- P0-4 live 部分降级仍给真实 clean
- P0-5 Safety 多否决优先级错误
- P0-7 两套 Agent 并存、重复仲裁、最终决策来源不一致
"""

import asyncio
import json
from pathlib import Path

import agent_team
import orchestrator
from pv_model import compute_metrics

CONFIG_PATH = Path(__file__).parent.parent / "data" / "pv_config.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def make_context(
    quality="demo",
    forecast_quality="demo",
    air_quality="demo",
    theoretical=None,
    pm10=135.0,
    rain=0.0,
    wind=9.0,
    simulated_records=False,
):
    days = [
        {"date": f"D{i+1}", "irradiance": 5.8, "rain": rain if i == 0 else 0.0, "wind": wind, "cloud": 0}
        for i in range(3)
    ]
    records = []
    if simulated_records:
        records.append({
            "source": "fallback-builtin",
            "data_kind": "simulation",
            "is_simulated": True,
            "status": "ok",
            "fetched_at": "t",
            "valid_time": "降级样例",
        })
    return {
        "forecast": {"days": days, "source": "test", "quality": forecast_quality, "fetched_at": "t"},
        "air": {"pm10": pm10, "dust": 120.0, "quality": air_quality, "source": "test"},
        "theoretical": theoretical,
        "quality": quality,
        "fetched_at": "t",
        "data_source_records": records,
    }


def _collect_events(monkeypatch, overrides):
    monkeypatch.setattr(orchestrator, "MCP_ENABLED", False)
    events = []

    async def collect():
        async for e in orchestrator.stream_decision(overrides):
            events.append(e)

    asyncio.run(collect())
    return events


# ---------------------------------------------------------------------------
# P0-1：数据不足时在 Agent 团队执行前短路
# ---------------------------------------------------------------------------

def test_p0_1_insufficient_data_skips_agent_team(monkeypatch):
    """数据不足时，事件流中不得出现 agent_result / agent_decision（七 Agent 不执行）。"""
    async def fake_fetch(lat, lng, loss_pct=10.0):
        return {
            "forecast": {"days": [], "source": "fallback", "quality": "fallback", "fetched_at": "t"},
            "air": {"pm10": None, "dust": None, "quality": "fallback", "fetched_at": "t"},
            "theoretical": None,
            "quality": "fallback",
            "fetched_at": "t",
            "data_source_records": [],
        }

    monkeypatch.setattr(orchestrator, "fetch_context", fake_fetch)
    events = _collect_events(monkeypatch, {
        "scenario": "live",
        "capacity_mw": 20,
        "days_since_clean": 20,
        "price_per_kwh": 0.25,
        "cleaning_cost": 4000,
    })
    types = [e["type"] for e in events]
    assert "agent_result" not in types, "数据不足时不应执行七 Agent"
    assert "agent_decision" not in types, "数据不足时不应输出 Agent 仲裁"
    final = [e for e in events if e["type"] == "final"][0]
    assert final["metrics"]["decision"]["action"] == "insufficient_data"
    # 只出现一次 round_start，不重复
    assert types.count("round_start") == 1


def test_p0_1_insufficient_data_no_none_conclusions(monkeypatch):
    """数据不足时，事件流中不得出现 'None%' / 'None 元' / '具备作业窗口' 等误导文字。"""
    async def fake_fetch(lat, lng, loss_pct=10.0):
        return {
            "forecast": {"days": [], "source": "fallback", "quality": "fallback", "fetched_at": "t"},
            "air": {"pm10": None, "dust": None, "quality": "fallback", "fetched_at": "t"},
            "theoretical": None,
            "quality": "fallback",
            "fetched_at": "t",
            "data_source_records": [],
        }

    monkeypatch.setattr(orchestrator, "fetch_context", fake_fetch)
    events = _collect_events(monkeypatch, {
        "scenario": "live",
        "capacity_mw": 20,
        "days_since_clean": 20,
        "price_per_kwh": 0.25,
        "cleaning_cost": 4000,
    })
    for e in events:
        text = json.dumps(e, ensure_ascii=False)
        assert "None%" not in text, "数据不足时不应输出 'None%'"
        assert "None 元" not in text, "数据不足时不应输出 'None 元'"
        assert "None MWh" not in text, "数据不足时不应输出 'None MWh'"


# ---------------------------------------------------------------------------
# P0-4：live 部分降级（关键源 fallback）即数据不足
# ---------------------------------------------------------------------------

def test_p0_4_live_degraded_forecast_fallback_returns_insufficient():
    """live 模式下预报为 fallback（空气质量正常）即数据不足。"""
    cfg = json.loads(json.dumps(CONFIG))
    cfg["scenario"] = "live"
    ctx = make_context(
        quality="live-degraded",
        forecast_quality="fallback",
        air_quality="live",
        theoretical={"E_d": 3.79, "month": 11},
    )
    m = compute_metrics(cfg, ctx)
    assert m["decision"]["action"] == "insufficient_data"
    assert any("模拟" in p or "降级" in p for p in m["decision"]["data_insufficient"])


def test_p0_4_live_degraded_air_fallback_returns_insufficient():
    """live 模式下空气质量为 fallback（预报正常）即数据不足。"""
    cfg = json.loads(json.dumps(CONFIG))
    cfg["scenario"] = "live"
    ctx = make_context(
        quality="live-degraded",
        forecast_quality="live",
        air_quality="fallback",
        theoretical={"E_d": 3.79, "month": 11},
    )
    m = compute_metrics(cfg, ctx)
    assert m["decision"]["action"] == "insufficient_data"


def test_p0_4_live_all_sources_ok_still_decides():
    """live 模式下全部关键源正常时仍正常决策（不误伤）。"""
    cfg = json.loads(json.dumps(CONFIG))
    cfg["scenario"] = "live"
    ctx = make_context(
        quality="live-good",
        forecast_quality="live",
        air_quality="live",
        theoretical={"E_d": 3.79, "month": 11},
    )
    m = compute_metrics(cfg, ctx)
    assert m["decision"]["action"] != "insufficient_data"


def test_p0_4_safety_vetoes_live_with_simulated_records():
    """live 模式下 Safety 对含模拟记录的数据源执行 data_quality 否决（兜底）。"""
    cfg = json.loads(json.dumps(CONFIG))
    cfg["scenario"] = "live"
    ctx = make_context(
        quality="live-degraded",
        forecast_quality="live",
        air_quality="live",
        simulated_records=True,
    )
    m = compute_metrics(cfg, ctx)
    safety = agent_team.run_safety_agent(m, cfg)
    assert safety["recommendation"] == "veto"
    assert safety["veto_type"] == "data_quality"


def test_p0_4_demo_mode_safety_does_not_veto():
    """demo 模式下 Safety 不因模拟数据否决（演示场景允许模拟数据）。"""
    cfg = json.loads(json.dumps(CONFIG))
    cfg["scenario"] = "demo"
    ctx = make_context(quality="demo", simulated_records=True)
    m = compute_metrics(cfg, ctx)
    safety = agent_team.run_safety_agent(m, cfg)
    assert safety["recommendation"] == "clear"


# ---------------------------------------------------------------------------
# P0-5：数据质量否决优先级高于天气否决
# ---------------------------------------------------------------------------

def test_p0_5_data_quality_veto_priority_over_weather():
    """live 模式下含模拟源 + 天气阻塞时，Safety 应以 data_quality 否决（而非 weather）。"""
    cfg = json.loads(json.dumps(CONFIG))
    cfg["scenario"] = "live"
    ctx = make_context(
        quality="live-degraded",
        forecast_quality="live",
        air_quality="live",
        rain=5.0,
        wind=15.0,
        simulated_records=True,
    )
    m = compute_metrics(cfg, ctx)
    # 天气确实阻塞（defer），但 Safety 的否决类型应为 data_quality
    assert m["decision"]["action"] == "defer"
    safety = agent_team.run_safety_agent(m, cfg)
    assert safety["recommendation"] == "veto"
    assert safety["veto_type"] == "data_quality", "数据质量否决应优先于天气否决"


def test_p0_5_weather_veto_when_no_simulated_sources():
    """无模拟源时，天气阻塞仍正常触发 weather 否决（不误伤）。"""
    cfg = json.loads(json.dumps(CONFIG))
    ctx = make_context(quality="demo", rain=5.0, wind=15.0)
    m = compute_metrics(cfg, ctx)
    safety = agent_team.run_safety_agent(m, cfg)
    assert safety["recommendation"] == "veto"
    assert safety["veto_type"] == "weather"


# ---------------------------------------------------------------------------
# P0-7：session_start 列出七 Agent；两轮决策记录一致
# ---------------------------------------------------------------------------

def test_p0_7_session_start_lists_seven_agents(monkeypatch):
    """session_start 事件应列出七个 Agent，而非旧四 Agent。"""
    events = _collect_events(monkeypatch, {
        "scenario": "demo",
        "capacity_mw": 20,
        "days_since_clean": 20,
        "price_per_kwh": 0.25,
        "cleaning_cost": 4000,
    })
    session = events[0]
    assert session["type"] == "session_start"
    agent_ids = {a["id"] for a in session["agents"]}
    assert agent_ids == {"weather", "soiling", "pv_performance", "economics", "safety", "critic", "decision"}


def test_p0_7_agent_execution_records_both_rounds(monkeypatch):
    """高成本触发第二轮分区修订时，agent_execution 记录 first_round_action 与 final_action。"""
    events = _collect_events(monkeypatch, {
        "scenario": "demo",
        "capacity_mw": 20,
        "days_since_clean": 20,
        "price_per_kwh": 0.25,
        "cleaning_cost": 45000,
    })
    final = [e for e in events if e["type"] == "final"][0]
    ae = final["metrics"].get("agent_execution") or {}
    assert "first_round_action" in ae, "应记录第一轮 Decision Agent 仲裁结果"
    assert "final_action" in ae
    # 第一轮规则决策 hold（净收益负），第二轮分区修订为 clean
    assert ae["first_round_action"] == "hold"
    assert ae["final_action"] == "clean"
    # 最后一次 agent_decision 事件应与 final metrics 一致
    decisions = [e for e in events if e["type"] == "agent_decision"]
    assert decisions[-1]["final_action"] == final["metrics"]["decision"]["action"]
    assert decisions[-1].get("second_round_revision") is True


def test_p0_7_no_revision_keeps_single_decision(monkeypatch):
    """正常场景（无第二轮修订）只输出一次 agent_decision，不重复。"""
    events = _collect_events(monkeypatch, {
        "scenario": "demo",
        "capacity_mw": 20,
        "days_since_clean": 20,
        "price_per_kwh": 0.25,
        "cleaning_cost": 4000,
    })
    decisions = [e for e in events if e["type"] == "agent_decision"]
    assert len(decisions) == 1, "无修订时不应重复输出 agent_decision"
    final = [e for e in events if e["type"] == "final"][0]
    ae = final["metrics"].get("agent_execution") or {}
    assert ae["first_round_action"] == ae["final_action"] == "clean"
