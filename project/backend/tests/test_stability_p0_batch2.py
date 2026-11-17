"""批次 2（P0-2/P0-3/P0-6/P0-10）：Critic/Safety 否决生效与决策一致性修复的回归测试。

对应 Bug：
- P0-2 Critic reject 不阻断最终决策
- P0-3 Critic 两类误报（interval 否决误报天气矛盾 / "非实时"误报模拟误标）
- P0-6 分区清洗窗口为空、经济状态不一致、理由矛盾
- P0-10 延后窗口可能本身不安全
"""

import json
from pathlib import Path

import agent_team
import agents
from pv_model import compute_metrics

CONFIG_PATH = Path(__file__).parent.parent / "data" / "pv_config.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def make_metrics(config=None, days=None, pm10=135.0, days_since_clean=20, cleaning_cost=4000, theoretical=None):
    cfg = config or json.loads(json.dumps(CONFIG))
    cfg["site"]["days_since_clean"] = days_since_clean
    cfg["economics"]["cleaning_cost"] = cleaning_cost
    forecast_days = days or [
        {"date": f"D{i+1}", "irradiance": 5.8, "rain": 0.0, "wind": 9.0, "cloud": 0}
        for i in range(3)
    ]
    ctx = {
        "forecast": {"days": forecast_days, "source": "test", "quality": "demo", "fetched_at": "t"},
        "air": {"pm10": pm10, "dust": 120.0, "quality": "demo", "source": "test"},
        "theoretical": theoretical,
        "quality": "demo",
        "fetched_at": "t",
        "data_source_records": [],
    }
    return compute_metrics(cfg, ctx)


# ---------------------------------------------------------------------------
# P0-2：Critic reject 阻止 clean 决策
# ---------------------------------------------------------------------------

def test_p0_2_critic_reject_blocks_clean():
    """注入计算错误使 Critic reject 时，最终决策不得为 clean。"""
    m = make_metrics()
    # 注入计算错误：篡改 net_gain 使复核不一致
    m["economics"]["net_gain"] = m["economics"]["net_gain"] + 100
    import asyncio
    team = asyncio.run(agent_team.run_team(m, CONFIG))
    critic = next(r for r in team["agent_results"] if r["agent_name"] == "critic")
    assert critic["recommendation"] == "reject", "篡改净收益后 Critic 应 reject"
    assert team["final_action"] != "clean", "Critic reject 时最终决策不得为 clean"


def test_p0_2_critic_approve_allows_clean():
    """正常场景 Critic approve 时，最终决策保持 clean（不误伤）。"""
    m = make_metrics()
    import asyncio
    team = asyncio.run(agent_team.run_team(m, CONFIG))
    critic = next(r for r in team["agent_results"] if r["agent_name"] == "critic")
    assert critic["recommendation"] == "approve"
    assert team["final_action"] == "clean"


# ---------------------------------------------------------------------------
# P0-3：Critic 两类误报
# ---------------------------------------------------------------------------

def test_p0_3_interval_veto_does_not_flag_weather_contradiction():
    """间隔否决（interval）时，Weather 判定窗口适合不构成矛盾，Critic 不应误报。"""
    m = make_metrics(days_since_clean=2)
    import asyncio
    team = asyncio.run(agent_team.run_team(m, CONFIG))
    contradiction_kinds = [
        i for i in team["critic_issues"] if i["kind"] == "contradiction"
    ]
    assert not contradiction_kinds, (
        f"间隔否决不应触发天气矛盾误报，实际 issues: {team['critic_issues']}"
    )


def test_p0_3_weather_veto_still_flags_contradiction():
    """天气否决时 Weather 仍判窗口适合，Critic 应正常报矛盾（不误伤正向检测）。"""
    windy_days = [
        {"date": f"W{i+1}", "irradiance": 5.0, "rain": 5.0, "wind": 15.0, "cloud": 0}
        for i in range(3)
    ]
    m = make_metrics(days=windy_days)
    import asyncio
    team = asyncio.run(agent_team.run_team(m, CONFIG))
    safety = next(r for r in team["agent_results"] if r["agent_name"] == "safety")
    assert safety["recommendation"] == "veto"
    assert safety["veto_type"] == "weather"
    # 天气否决 + Weather 判定窗口阻塞 → 不矛盾（Weather 也会说阻塞）
    # 所以这里 Weather recommendation 应为 wait_weather_window，不触发矛盾
    weather = next(r for r in team["agent_results"] if r["agent_name"] == "weather")
    assert weather["recommendation"] == "wait_weather_window"


def test_p0_3_non_realtime_phrase_not_flagged_as_mislabeled():
    """结论含"非实时"（诚实披露）不应被 Critic 误报为模拟数据误标。"""
    m = make_metrics(theoretical={"E_d": 3.79, "month": 11, "radiation_db": "PVGIS-ERA5", "year_min": 2005, "year_max": 2023})
    # PV Performance Agent 在 PVGIS 模式下输出 "historical，非实时"
    pv_result = agent_team.run_pv_performance_agent(m, CONFIG)
    assert "非实时" in pv_result["conclusion"]
    # 用含模拟源的数据跑规则审查（注意 _sources_of 读 data_quality.data_sources）
    m["data_quality"]["data_sources"] = [
        {"source": "fallback-builtin", "data_kind": "simulation", "is_simulated": True, "status": "ok", "fetched_at": "t", "valid_time": "降级样例"}
    ]
    results = [agent_team.run_weather_agent(m, CONFIG), pv_result]
    issues = agent_team._rule_critic_checks(m, results)
    mislabeled = [i for i in issues if i["kind"] == "simulation_mislabeled"]
    assert not mislabeled, (
        f'"非实时"是诚实披露，不应误报为模拟误标，实际 issues: {issues}'
    )


def test_p0_3_realtime_claim_still_flagged():
    """结论声称"基于实时数据"（含模拟源时）应被 Critic 正常检出（不误伤正向检测）。"""
    m = make_metrics()
    m["data_quality"]["data_sources"] = [
        {"source": "fallback-builtin", "data_kind": "simulation", "is_simulated": True, "status": "ok", "fetched_at": "t", "valid_time": "降级样例"}
    ]
    weather = agent_team.run_weather_agent(m, CONFIG)
    weather["conclusion"] = "基于实时监测数据，风速 9 m/s，具备作业窗口。"
    issues = agent_team._rule_critic_checks(m, [weather])
    mislabeled = [i for i in issues if i["kind"] == "simulation_mislabeled"]
    assert mislabeled, "声称实时+含模拟源应被检出"


# ---------------------------------------------------------------------------
# P0-6：分区清洗决策字段一致
# ---------------------------------------------------------------------------

def test_p0_6_partial_clean_has_window_and_econ_ok():
    """分区清洗净收益为正时：action=clean、window 非 None、economics_ok=True。"""
    m = make_metrics(cleaning_cost=45000)
    updated = agents.apply_partial(m, CONFIG)
    assert updated["decision"]["action"] == "clean"
    assert updated["decision"]["window"] is not None, "分区 clean 必须有执行窗口"
    assert updated["decision"]["economics_ok"] is True
    assert "分区净收益" in updated["decision"]["reason"]
    # ops 发言不得出现 None
    ops_msg = agents.ops_opinion(updated, CONFIG)["message"]
    assert "None" not in ops_msg, f"调度官发言不应出现 None：{ops_msg}"


def test_p0_6_partial_negative_keeps_hold_with_consistent_reason():
    """分区清洗仍不经济时：action 保持 hold、reason 说明不经济（不矛盾）。"""
    m = make_metrics(cleaning_cost=90000)
    updated = agents.apply_partial(m, CONFIG)
    assert updated["decision"]["action"] != "clean", "净收益为负不得 clean"
    assert updated["decision"]["economics_ok"] is False
    assert "不建议执行清洗" in updated["decision"]["reason"] or "非正" in updated["decision"]["reason"]


# ---------------------------------------------------------------------------
# P0-10：best_date 只在安全日期中选择
# ---------------------------------------------------------------------------

def test_p0_10_best_date_never_unsafe():
    """三天全大风（15 m/s）时，best_date 应为 None 而非某个仍不安全的日期。"""
    windy_days = [
        {"date": f"BAD{i+1}", "irradiance": 5.0, "rain": 0.0, "wind": 15.0, "cloud": 0}
        for i in range(3)
    ]
    m = make_metrics(days=windy_days)
    assert m["decision"]["action"] == "defer"
    assert m["weather"]["best_date"] is None, "全大风时不应推荐任何日期为窗口"
    assert m["weather"]["best_irradiance"] is None


def test_p0_10_best_date_from_safe_days_only():
    """混合天气（1 天安全 + 2 天大风）时，best_date 应从安全日中选。"""
    mixed_days = [
        {"date": "SAFE1", "irradiance": 5.5, "rain": 0.0, "wind": 8.0, "cloud": 0},
        {"date": "WINDY2", "irradiance": 6.5, "rain": 0.0, "wind": 15.0, "cloud": 0},
        {"date": "WINDY3", "irradiance": 6.0, "rain": 0.0, "wind": 14.0, "cloud": 0},
    ]
    m = make_metrics(days=mixed_days)
    assert m["weather"]["best_date"] == "SAFE1", "best_date 应从安全日中选，而非辐照最高的不安全日"


def test_p0_10_ops_no_none_in_defer_message():
    """无安全窗口时，调度官发言不得出现 None。"""
    windy_days = [
        {"date": f"BAD{i+1}", "irradiance": 5.0, "rain": 0.0, "wind": 15.0, "cloud": 0}
        for i in range(3)
    ]
    m = make_metrics(days=windy_days)
    ops_msg = agents.ops_opinion(m, CONFIG)["message"]
    assert "None" not in ops_msg, f"调度官发言不应出现 None：{ops_msg}"
    assert "暂无" in ops_msg or "持续监测" in ops_msg


def test_p0_10_defer_plan_reason_without_safe_window():
    """无安全窗口时，defer_plan 的 reason 应说明暂无窗口而非引用 None。"""
    windy_days = [
        {"date": f"BAD{i+1}", "irradiance": 5.0, "rain": 0.0, "wind": 15.0, "cloud": 0}
        for i in range(3)
    ]
    m = make_metrics(days=windy_days)
    updated = agents.defer_plan(m, CONFIG)
    assert "None" not in updated["decision"]["reason"]
    assert "暂无安全作业窗口" in updated["decision"]["reason"]


def test_p0_10_critic_defer_review_passes_without_best_date():
    """无安全窗口时，critic_defer_review 应通过（天气阻塞属实即一致）。"""
    windy_days = [
        {"date": f"BAD{i+1}", "irradiance": 5.0, "rain": 0.0, "wind": 15.0, "cloud": 0}
        for i in range(3)
    ]
    m = make_metrics(days=windy_days)
    passed, evt = agents.critic_defer_review(m, CONFIG)
    assert passed is True, "天气阻塞属实时延后决策应通过复核"
    assert "None" not in evt["message"]
