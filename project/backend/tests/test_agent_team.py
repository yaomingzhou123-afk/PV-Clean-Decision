import asyncio
import json
from pathlib import Path

import agent_team
import llm as llm_mod
from agent_team import (
    AGENT_TEAM_META,
    REQUIRED_FIELDS,
    _parse_llm_issues,
    _validate_result,
    run_decision_agent,
    run_safety_agent,
    run_team,
    to_speak_event,
)
from pv_model import compute_metrics
from weather import demo_context

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "data" / "pv_config.json").read_text(encoding="utf-8"))


def make_metrics(days=20, rain=0.0, wind=9.0):
    cfg = json.loads(json.dumps(CONFIG))
    cfg["site"]["days_since_clean"] = days
    days_list = [
        {"date": f"D{i+1}", "irradiance": 5.8, "rain": rain, "wind": wind, "cloud": 10, "temp_max": 5.0, "temp_min": -2.0}
        for i in range(3)
    ]
    ctx = {
        "forecast": {"days": days_list, "source": "demo", "quality": "demo", "fetched_at": "t"},
        "air": {"pm10": 135.0, "pm2_5": 24.0, "dust": 120.0, "source": "demo", "quality": "demo"},
        "theoretical": None,
        "quality": "demo",
        "fetched_at": "t",
        "data_source_records": [
            {"source": "demo-builtin", "data_kind": "simulation", "is_simulated": True, "status": "ok", "fetched_at": "t", "valid_time": "演示 3 天"},
        ],
    }
    return compute_metrics(cfg, ctx), cfg


def run(coro):
    return asyncio.run(coro)


def test_team_runs_seven_agents_in_order():
    m, cfg = make_metrics()
    team = run(run_team(m, cfg))
    assert team["order"] == ["weather", "soiling", "pv_performance", "economics", "safety", "critic", "decision"]
    assert len(team["agent_results"]) == 7
    assert all(r["status"] == "ok" for r in team["agent_results"])


def test_every_agent_result_has_required_structure():
    m, cfg = make_metrics()
    team = run(run_team(m, cfg))
    for r in team["agent_results"]:
        for field in REQUIRED_FIELDS:
            assert field in r, f"{r['agent_name']} 缺字段 {field}"
        assert r["confidence_type"] in ("heuristic", "none")


def test_agents_read_unified_metrics_input():
    m, cfg = make_metrics()
    team = run(run_team(m, cfg))
    by_name = {r["agent_name"]: r for r in team["agent_results"]}
    assert by_name["weather"]["inputs_read"]["weather"]["wind_max"] == 9.0
    assert by_name["soiling"]["inputs_read"]["soiling"]["pm10"] == 135.0
    assert by_name["economics"]["inputs_read"]["economics"]["cleaning_cost"] == 4000


def test_critic_detects_real_calculation_error():
    m, cfg = make_metrics()
    m["economics"]["net_gain"] = 12345.0
    team = run(run_team(m, cfg))
    kinds = [i["kind"] for i in team["critic_issues"]]
    assert "calculation_error" in kinds
    critic = next(r for r in team["agent_results"] if r["agent_name"] == "critic")
    assert critic["recommendation"] == "reject"


def test_critic_detects_simulation_mislabeled_as_realtime():
    m, cfg = make_metrics()
    results = [
        agent_team.run_weather_agent(m, cfg),
        agent_team.run_safety_agent(m, cfg),
    ]
    results[0]["conclusion"] = "基于实时监测数据，风速 9 m/s 适合清洗。"
    issues = agent_team._rule_critic_checks(m, results)
    assert any(i["kind"] == "simulation_mislabeled" for i in issues)


def test_safety_agent_vetoes_on_wind():
    m, cfg = make_metrics(wind=15.0)
    safety = run_safety_agent(m, cfg)
    assert safety["recommendation"] == "veto"
    assert safety["veto_type"] == "weather"


def test_safety_agent_vetoes_on_interval():
    m, cfg = make_metrics(days=2)
    safety = run_safety_agent(m, cfg)
    assert safety["recommendation"] == "veto"
    assert safety["veto_type"] == "interval"


def test_decision_agent_respects_safety_veto():
    m, cfg = make_metrics(wind=15.0)
    team = run(run_team(m, cfg))
    assert team["veto_applied"] is True
    assert team["final_action"] == "defer"
    assert team["decision_trace"][0]["value"] == "weather"


def test_decision_matches_rules_when_no_veto():
    m, cfg = make_metrics()
    team = run(run_team(m, cfg))
    assert team["veto_applied"] is False
    assert team["final_action"] == m["decision"]["action"]


def test_llm_failure_falls_back_to_rules(monkeypatch):
    async def broken(system, user, temperature=0.4):
        raise RuntimeError("LLM 不可用")

    monkeypatch.setattr(llm_mod, "enabled", lambda: True)
    monkeypatch.setattr(llm_mod, "chat", broken)
    m, cfg = make_metrics()
    team = run(run_team(m, cfg))
    assert team["llm_enhanced"] is False
    assert team["final_action"] == "clean"
    assert len(team["agent_results"]) == 7


def test_llm_invalid_output_is_rejected():
    assert _parse_llm_issues("不是 JSON") is None
    assert _parse_llm_issues('{"wrong": []}') is None
    assert _parse_llm_issues('{"issues": [{"agent": "x", "issue": 123}]}') is None


def test_llm_valid_output_parsed():
    parsed = _parse_llm_issues('{"issues": [{"agent": "economics", "issue": "收益口径可疑", "severity": "high"}]}')
    assert parsed and parsed[0]["agent"] == "economics"
    assert parsed[0]["severity"] == "high"


def test_invalid_agent_output_marked_error_not_used():
    bad = {"agent_name": "weather", "status": "unknown_status"}
    assert _validate_result(bad) is None


def test_confidence_is_heuristic_never_probability():
    m, cfg = make_metrics()
    team = run(run_team(m, cfg))
    for r in team["agent_results"]:
        if r.get("confidence") is not None:
            assert r["confidence_type"] == "heuristic"


def test_to_speak_event_compatible_shape():
    m, cfg = make_metrics()
    team = run(run_team(m, cfg))
    for r in team["agent_results"]:
        evt = to_speak_event(r)
        assert evt["type"] == "agent_speak"
        assert evt["agent"] == r["agent_name"]
        assert evt["stance"] in ("support", "object", "propose")
        assert isinstance(evt["message"], str) and evt["message"]


def test_soiling_agent_declares_model_estimate():
    m, cfg = make_metrics()
    team = run(run_team(m, cfg))
    soiling = next(r for r in team["agent_results"] if r["agent_name"] == "soiling")
    assert "model_estimate" in soiling["conclusion"]
    assert "非传感器实测" in soiling["conclusion"]


def test_decision_trace_is_complete_and_traceable():
    m, cfg = make_metrics()
    team = run(run_team(m, cfg))
    trace = team["decision_trace"]
    assert {t["factor"] for t in trace} >= {"安全否决", "污损水平", "经济性", "基础规则决策", "Critic 审查"}
    assert all(t.get("source") and t.get("value") is not None for t in trace)


def test_llm_max_calls_limited():
    assert agent_team.LLM_CRITIC_MAX_CALLS == 1


def test_main_decision_api_invokes_team(monkeypatch):
    """证明主决策 API 实际调用 agent_team（不是展示层）。"""
    import orchestrator

    calls = {"n": 0}
    original = orchestrator.run_team

    async def spy(metrics, config):
        calls["n"] += 1
        return await original(metrics, config)

    monkeypatch.setattr(orchestrator, "run_team", spy)

    async def consume():
        events = []
        async for evt in orchestrator.stream_decision(
            {"scenario": "demo", "capacity_mw": 20, "days_since_clean": 20, "price_per_kwh": 0.25, "cleaning_cost": 4000}
        ):
            events.append(evt)
        return events

    events = run(consume())
    assert calls["n"] == 1, "主决策链路必须调用 run_team"
    agent_results = [e for e in events if e["type"] == "agent_result"]
    assert len(agent_results) == 7
    speaks = [e for e in events if e["type"] == "agent_speak"]
    assert len(speaks) >= 7
    final = [e for e in events if e["type"] == "final"][-1]
    assert "agent_execution" in final["metrics"]
    assert final["metrics"]["agent_execution"]["order"][-1] == "decision"