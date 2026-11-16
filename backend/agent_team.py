"""V3.0 第五阶段：多 Agent 团队（真实接入主决策链路）。

设计原则：
1. 七个 Agent 全部由确定性 Python 规则实现，读取统一 metrics/config 输入，输出统一结构。
2. LLM 仅作为 Critic 的可选增强（发现质疑点），输出必须通过结构校验；LLM 不可用时规则
   Critic 独立完成审查，决策链路不受影响。
3. 关键数学计算全部来自 pv_model（确定性模块），Agent 只做分析、解释、审查与裁决，
   不得自行产生天气/辐照/成本/污损数值。
4. 置信度为启发式评分（confidence_type="heuristic"），未经统计校准，绝不冒充真实概率。
"""

import json
import time

import llm

AGENT_TEAM_META = {
    "weather": {"name": "Weather Agent", "goal": "获取并分析天气、降雨、风速与辐照，说明数据时间与来源"},
    "soiling": {"name": "Soiling Agent", "goal": "分析 PM10、PM2.5、沙尘与无雨天数，给出污损风险估算，区分实测与估算"},
    "pv_performance": {"name": "PV Performance Agent", "goal": "根据辐照、装机参数与污损估算，分析潜在发电损失"},
    "economics": {"name": "Economic Agent", "goal": "基于确定性经济计算，分析清洗成本、增量收益、净收益与回收期"},
    "safety": {"name": "Operation & Safety Agent", "goal": "检查用户配置的安全阈值、风速、降雨与数据质量，必要时否决"},
    "critic": {"name": "Critic Agent", "goal": "审查证据、数据来源、单位、结论矛盾、模拟数据误标与计算错误"},
    "decision": {"name": "Decision Agent", "goal": "汇总全部结果，遵守安全否决，输出最终清洗决策与可追溯理由"},
}

REQUIRED_FIELDS = (
    "agent_name",
    "status",
    "conclusion",
    "evidence",
    "data_sources",
    "assumptions",
    "uncertainties",
    "recommendation",
    "confidence_type",
)

LLM_CRITIC_MAX_CALLS = 1

_CONSERVATIVE_RANK = {"clean": 0, "hold": 1, "defer": 2, "insufficient_data": 3}


def _now() -> float:
    return round(time.time(), 3)


def _validate_result(result: dict) -> dict | None:
    """Agent 输出合规校验：缺字段或类型错误返回 None（调用方标记 error，不进入决策）。"""
    if not isinstance(result, dict):
        return None
    for field in REQUIRED_FIELDS:
        if field not in result:
            return None
    if result["status"] not in ("ok", "error", "skipped"):
        return None
    if not isinstance(result["conclusion"], str) or not result["conclusion"].strip():
        return None
    for list_field in ("evidence", "data_sources", "assumptions", "uncertainties"):
        if not isinstance(result[list_field], list):
            return None
    if result["confidence_type"] not in ("heuristic", "none"):
        return None
    return result


def _result(
    agent: str,
    conclusion: str,
    evidence: list,
    data_sources: list,
    assumptions: list,
    uncertainties: list,
    recommendation: str,
    confidence: float | None,
    inputs_read: dict,
    status: str = "ok",
    veto_type: str | None = None,
) -> dict:
    return {
        "agent_name": agent,
        "role": AGENT_TEAM_META[agent]["name"],
        "goal": AGENT_TEAM_META[agent]["goal"],
        "status": status,
        "conclusion": conclusion,
        "evidence": evidence,
        "data_sources": data_sources,
        "assumptions": assumptions,
        "uncertainties": uncertainties,
        "recommendation": recommendation,
        "confidence_type": "heuristic" if confidence is not None else "none",
        "confidence": confidence,
        "inputs_read": inputs_read,
        "veto_type": veto_type,
        "ts": _now(),
    }


def _ev(metric: str, value, threshold, unit: str, verdict: str) -> dict:
    return {"metric": metric, "value": value, "threshold": threshold, "unit": unit, "verdict": verdict}


def _sources_of(metrics: dict) -> list:
    records = (metrics.get("data_quality") or {}).get("data_sources") or []
    return [
        {
            "source": r.get("source"),
            "data_kind": r.get("data_kind"),
            "is_simulated": bool(r.get("is_simulated")),
            "status": r.get("status"),
            "fetched_at": r.get("fetched_at"),
            "valid_time": r.get("valid_time"),
        }
        for r in records
    ]


def _simulated_present(sources: list) -> bool:
    return any(s.get("is_simulated") for s in sources)


# ---------------------------------------------------------------------------
# 1. Weather Agent
# ---------------------------------------------------------------------------

def run_weather_agent(metrics: dict, config: dict) -> dict:
    w = metrics["weather"]
    safety = config["safety"]
    sources = _sources_of(metrics)
    rain_blocked = (w.get("rain_next48") or 0) >= safety["rain_limit_mm"]
    wind_blocked = (w.get("wind_max") or 0) >= safety["wind_limit_ms"]
    blocked = rain_blocked or wind_blocked
    if blocked:
        reason = "降水超阈值" if rain_blocked else ""
        if wind_blocked:
            reason = (reason + "、" if reason else "") + "风速超安全阈值"
        conclusion = (
            f"未来 48 小时降水 {w['rain_next48']} mm、最大风速 {w['wind_max']} m/s（{reason}），"
            f"不具备清洗作业窗口。数据来源 {w.get('source')}，拉取时间 {w.get('fetched_at')}，"
            f"覆盖 {w['days'][0]['date'] if w.get('days') else '--'} 起三天预报。"
        )
        recommendation = "wait_weather_window"
        margin = min(
            abs((w["rain_next48"] or 0) - safety["rain_limit_mm"]) / max(safety["rain_limit_mm"], 0.1),
            abs((w["wind_max"] or 0) - safety["wind_limit_ms"]) / max(safety["wind_limit_ms"], 0.1),
        )
    else:
        conclusion = (
            f"未来 48 小时降水 {w['rain_next48']} mm（阈值 {safety['rain_limit_mm']}）、"
            f"最大风速 {w['wind_max']} m/s（阈值 {safety['wind_limit_ms']}）、辐照均值 {w.get('avg_irradiance')} kWh/m²，"
            f"具备作业窗口。数据来源 {w.get('source')}，拉取时间 {w.get('fetched_at')}，为 3 天预报（forecast，非实测）。"
        )
        recommendation = "window_suitable"
        margin = min(
            abs((w["rain_next48"] or 0) - safety["rain_limit_mm"]) / max(safety["rain_limit_mm"], 0.1),
            abs((w["wind_max"] or 0) - safety["wind_limit_ms"]) / max(safety["wind_limit_ms"], 0.1),
        )
    confidence = round(min(0.99, 0.6 + 0.4 * min(1.0, margin)), 2)
    evidence = [
        _ev("rain_next48", w.get("rain_next48"), safety["rain_limit_mm"], "mm", "exceed" if rain_blocked else "within"),
        _ev("wind_max", w.get("wind_max"), safety["wind_limit_ms"], "m/s", "exceed" if wind_blocked else "within"),
    ]
    return _result(
        "weather",
        conclusion,
        evidence,
        sources,
        assumptions=["预报数据按面插值代表站点，未做现场微气候修正"],
        uncertainties=["3 天预报存在固有误差，临近窗口需复核"],
        recommendation=recommendation,
        confidence=confidence,
        inputs_read={"weather": {"rain_next48": w.get("rain_next48"), "wind_max": w.get("wind_max"), "avg_irradiance": w.get("avg_irradiance"), "source": w.get("source")}},
    )


# ---------------------------------------------------------------------------
# 2. Soiling Agent
# ---------------------------------------------------------------------------

def run_soiling_agent(metrics: dict, config: dict) -> dict:
    s = metrics["soiling"]
    soiling_cfg = config["soiling"]
    threshold = soiling_cfg["low_soiling_threshold_pct"]
    min_interval = soiling_cfg.get("min_clean_interval_days", 14)
    sources = _sources_of(metrics)
    method = s.get("method", "model_estimate")
    interval_short = (s.get("days") or 0) < min_interval
    significant = (s.get("loss_pct") or 0) >= threshold

    if interval_short:
        conclusion = (
            f"距上次清洗 {s['days']} 天，低于最小清洗间隔 {min_interval} 天；估算污损损失 {s['loss_pct']}%。"
            f"本值为模型估算（method={method}），非传感器实测。"
        )
        recommendation = "hold_interval"
    elif not significant:
        conclusion = (
            f"估算污损损失 {s['loss_pct']}%，低于显著阈值 {threshold}%；PM10 {s.get('pm10')} μg/m³。"
            f"本值为模型估算（method={method}），非传感器实测， Drivers：{'；'.join(s.get('drivers', [])[:2])}。"
        )
        recommendation = "not_significant"
    else:
        conclusion = (
            f"估算污损损失 {s['loss_pct']}%（阈值 {threshold}%），PM10 {s.get('pm10')} μg/m³，已形成明显发电损失。"
            f"本值为模型估算（method={method}），非传感器实测。"
        )
        recommendation = "significant"
    margin = abs((s.get("loss_pct") or 0) - threshold) / max(threshold, 0.1)
    confidence = round(min(0.99, 0.6 + 0.4 * min(1.0, margin)), 2)
    evidence = [
        _ev("soiling_loss_pct", s.get("loss_pct"), threshold, "%", "above" if significant else "below"),
        _ev("days_since_clean", s.get("days"), min_interval, "天", "below" if interval_short else "within"),
        _ev("pm10", s.get("pm10"), soiling_cfg["pm10_ref"], "μg/m³", "above" if (s.get("pm10") or 0) > soiling_cfg["pm10_ref"] else "within"),
    ]
    return _result(
        "soiling",
        conclusion,
        evidence,
        sources,
        assumptions=[(s.get("param_basis") or {}).get("base_rate_per_day", "基础速率参数为公开研究区间保守值")],
        uncertainties=(s.get("limitations") or ["线性累积假设，未建模沙尘事件突发性"])[:3],
        recommendation=recommendation,
        confidence=confidence,
        inputs_read={"soiling": {"loss_pct": s.get("loss_pct"), "pm10": s.get("pm10"), "days": s.get("days"), "method": method, "natural_clean_expected": s.get("natural_clean_expected")}},
    )


# ---------------------------------------------------------------------------
# 3. PV Performance Agent
# ---------------------------------------------------------------------------

def run_pv_performance_agent(metrics: dict, config: dict) -> dict:
    e = metrics["economics"]
    s = metrics["soiling"]
    sources = _sources_of(metrics)
    theory = e.get("theory_mwh_day")
    source_kind = e.get("theoretical_source")
    if source_kind == "pvgis":
        basis = "PVGIS 历史气候均值（ERA5 2005–2023，historical，非实时）"
    else:
        basis = "预报辐照降级公式（估算，含系统效率假设）"
    recoverable = e.get("recoverable_mwh_day")
    conclusion = (
        f"理论日发电量 {theory} MWh（依据：{basis}）；当前估算污损损失 {s.get('loss_pct')}%，"
        f"对应潜在发电损失约 {recoverable} MWh/日（按恢复效率 {e.get('recovery_efficiency')} 与"
        f"自然清洁折减 {e.get('natural_clean_discount')} 修正后的可恢复口径）。"
    )
    evidence = [
        _ev("theory_mwh_day", theory, None, "MWh/日", "reference"),
        _ev("recoverable_mwh_day", recoverable, None, "MWh/日", "reference"),
        _ev("theoretical_source", source_kind, "pvgis", "-", "degraded" if source_kind != "pvgis" else "nominal"),
    ]
    margin = 0.5 if source_kind == "pvgis" else 0.2
    return _result(
        "pv_performance",
        conclusion,
        evidence,
        sources,
        assumptions=["发电量基准为均值口径，未计入当日实时出力曲线"],
        uncertainties=["实际损失取决于组件类型与局部遮挡分布，均值口径存在偏差"],
        recommendation="loss_estimated",
        confidence=round(min(0.99, 0.6 + 0.4 * margin), 2),
        inputs_read={"economics": {"theory_mwh_day": theory, "theoretical_source": source_kind, "recoverable_mwh_day": recoverable}, "soiling": {"loss_pct": s.get("loss_pct")}},
    )


# ---------------------------------------------------------------------------
# 4. Economic Agent
# ---------------------------------------------------------------------------

def run_economics_agent(metrics: dict, config: dict) -> dict:
    e = metrics["economics"]
    sources = _sources_of(metrics)
    net = e.get("net_gain")
    profitable = net is not None and net > 0
    breakdown = e.get("cost_breakdown") or {}
    if breakdown.get("mode") == "itemized":
        cost_desc = "分项成本：" + " + ".join(f"{k}={v}元" for k, v in (breakdown.get("items") or {}).items())
    else:
        cost_desc = f"包干成本 {e.get('cleaning_cost')} 元"
    conclusion = (
        f"评估期 {e.get('horizon_days')} 天增量收益 {e.get('horizon_revenue')} 元；{cost_desc}；"
        f"停机损失 {e.get('downtime_loss')} 元；净收益 {net} 元；回收期 {e.get('payback_days')} 天。"
        f"以上由确定性经济模块（pv_model）计算，本 Agent 仅复核与解释，不自行计算金额。"
    )
    margin = abs(net) / max(e.get("horizon_revenue") or 1, 1) if net is not None else 0.5
    confidence = round(min(0.99, 0.6 + 0.4 * min(1.0, margin)), 2)
    evidence = [
        _ev("net_gain", net, 0, "元", "above" if profitable else "below"),
        _ev("payback_days", e.get("payback_days"), e.get("horizon_days"), "天", "within" if (e.get("payback_days") or 0) <= (e.get("horizon_days") or 0) else "exceed"),
    ]
    return _result(
        "economics",
        conclusion,
        evidence,
        sources,
        assumptions=["电价与清洗成本为用户输入/配置值，按固定值评估，未计电价波动"],
        uncertainties=["增量收益依赖污损估算精度，污损偏差会线性传导至净收益"],
        recommendation="profitable" if profitable else "unprofitable",
        confidence=confidence,
        inputs_read={"economics": {"net_gain": net, "horizon_revenue": e.get("horizon_revenue"), "cleaning_cost": e.get("cleaning_cost"), "downtime_loss": e.get("downtime_loss"), "payback_days": e.get("payback_days")}},
    )


# ---------------------------------------------------------------------------
# 5. Operation & Safety Agent（否决权）
# ---------------------------------------------------------------------------

def run_safety_agent(metrics: dict, config: dict) -> dict:
    w = metrics["weather"]
    d = metrics["decision"]
    safety = config["safety"]
    sources = _sources_of(metrics)
    quality = (metrics.get("data_quality") or {}).get("overall_quality")

    veto_type = None
    veto_reason = ""
    rain_blocked = (w.get("rain_next48") or 0) >= safety["rain_limit_mm"]
    wind_blocked = (w.get("wind_max") or 0) >= safety["wind_limit_ms"]
    interval_blocked = bool(d.get("interval_block"))
    simulated_present = _simulated_present(sources)
    # P0-5 修复：数据质量否决优先级最高（数据不足 > 天气 > 间隔）；
    # P0-4 修复：live 模式下检查关键源是否含模拟记录，而非仅看整体 quality
    if config.get("scenario") == "live" and (quality in ("demo", "fallback") or simulated_present):
        veto_type = "data_quality"
        veto_reason = "live 模式下关键数据源含模拟记录，不基于模拟数据执行真实决策"
    elif rain_blocked or wind_blocked:
        veto_type = "weather"
        veto_reason = f"降水 {w['rain_next48']}mm ≥ {safety['rain_limit_mm']} 或风速 {w['wind_max']}m/s ≥ {safety['wind_limit_ms']}（用户配置阈值）"
    elif interval_blocked:
        veto_type = "interval"
        veto_reason = f"距上次清洗 {metrics['soiling'].get('days')} 天 < 最小间隔 {d.get('min_clean_interval_days')} 天"

    if veto_type:
        conclusion = f"否决清洗执行：{veto_reason}。安全约束优先级高于经济收益。"
        recommendation = "veto"
        margin = 0.8
    else:
        conclusion = (
            f"安全检查通过：风速 {w['wind_max']} m/s < {safety['wind_limit_ms']}（用户配置阈值）、"
            f"降水 {w['rain_next48']} mm < {safety['rain_limit_mm']}、间隔满足、数据质量 {quality}。"
        )
        recommendation = "clear"
        margin = min(
            abs(safety["wind_limit_ms"] - (w.get("wind_max") or 0)) / max(safety["wind_limit_ms"], 0.1),
            abs(safety["rain_limit_mm"] - (w.get("rain_next48") or 0)) / max(safety["rain_limit_mm"], 0.1),
        )
    evidence = [
        _ev("wind_max", w.get("wind_max"), safety["wind_limit_ms"], "m/s", "exceed" if wind_blocked else "within"),
        _ev("rain_next48", w.get("rain_next48"), safety["rain_limit_mm"], "mm", "exceed" if rain_blocked else "within"),
        _ev("days_since_clean", metrics["soiling"].get("days"), d.get("min_clean_interval_days"), "天", "below" if interval_blocked else "within"),
    ]
    return _result(
        "safety",
        conclusion,
        evidence,
        sources,
        assumptions=["安全阈值完全由用户配置决定，不代表行业统一标准"],
        uncertainties=["预报风速为日最大值口径，阵风瞬时超限风险未单独建模"],
        recommendation=recommendation,
        confidence=round(min(0.99, 0.6 + 0.4 * min(1.0, margin)), 2),
        inputs_read={"weather": {"wind_max": w.get("wind_max"), "rain_next48": w.get("rain_next48")}, "decision": {"interval_block": interval_blocked}, "safety_config": dict(safety)},
        veto_type=veto_type,
    )


# ---------------------------------------------------------------------------
# 6. Critic Agent（规则审查 + 可选 LLM 增强）
# ---------------------------------------------------------------------------

def _rule_critic_checks(metrics: dict, agent_results: list) -> list:
    """确定性审查：计算复核、结论矛盾、模拟数据误标、单位抽查。发现真实存在的问题。"""
    issues = []
    e = metrics.get("economics") or {}
    net = e.get("net_gain")
    horizon_rev = e.get("horizon_revenue")
    cost = e.get("cleaning_cost")
    downtime = e.get("downtime_loss")
    if None not in (net, horizon_rev, cost, downtime):
        recomputed = round(horizon_rev - cost - downtime, 0)
        if abs(recomputed - net) > 2.0:
            issues.append({
                "agent": "economics",
                "issue": f"计算复核不一致：净收益应为 {recomputed} 元，报告值为 {net} 元",
                "severity": "high",
                "kind": "calculation_error",
            })
    safety = next((r for r in agent_results if r["agent_name"] == "safety"), None)
    # P0-3 修复：只在天气否决时检查 Weather 结论矛盾；
    # interval/data_quality 否决与天气窗口无关，不应误报
    if safety and safety.get("recommendation") == "veto" and safety.get("veto_type") == "weather":
        conflicting = [r["agent_name"] for r in agent_results if r.get("recommendation") in ("window_suitable", "profitable") and r["agent_name"] in ("weather",)]
        if conflicting:
            issues.append({
                "agent": "/".join(conflicting),
                "issue": "结论矛盾：安全已否决，但 Weather Agent 仍判定窗口适合",
                "severity": "high",
                "kind": "contradiction",
            })
    sources = _sources_of(metrics)
    simulated = [s["source"] for s in sources if s.get("is_simulated")]
    if simulated:
        # P0-3 修复：排除"非实时"/"不是实时"等否定表述，只检测声称基于实时数据的结论
        mentions_live = [
            r["agent_name"] for r in agent_results
            if "实时" in r.get("conclusion", "")
            and "非实时" not in r.get("conclusion", "")
            and "不是实时" not in r.get("conclusion", "")
        ]
        if mentions_live:
            issues.append({
                "agent": "/".join(mentions_live),
                "issue": f"模拟数据误标：数据源 {', '.join(simulated)} 为 simulation，但结论声称基于实时数据",
                "severity": "high",
                "kind": "simulation_mislabeled",
            })
    unit_map = {"rain_next48": "mm", "wind_max": "m/s", "soiling_loss_pct": "%", "net_gain": "元", "pm10": "μg/m³"}
    for r in agent_results:
        for ev in r.get("evidence") or []:
            expected = unit_map.get(ev.get("metric"))
            if expected and ev.get("unit") != expected:
                issues.append({
                    "agent": r["agent_name"],
                    "issue": f"单位异常：{ev.get('metric')} 应为 {expected}，报告为 {ev.get('unit')}",
                    "severity": "medium",
                    "kind": "unit_error",
                })
    return issues


def _parse_llm_issues(text: str) -> list | None:
    """LLM 输出结构校验：仅接受 {"issues": [{agent, issue, severity}]}，不合规返回 None。"""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "issues" not in data or not isinstance(data["issues"], list):
        return None
    issues = []
    for item in data["issues"]:
        if not isinstance(item, dict):
            return None
        agent = item.get("agent")
        issue = item.get("issue")
        severity = item.get("severity", "medium")
        if not isinstance(agent, str) or not isinstance(issue, str) or not issue.strip():
            return None
        if severity not in ("high", "medium", "low"):
            severity = "medium"
        issues.append({"agent": agent, "issue": issue, "severity": severity, "kind": "llm_review"})
    return issues


async def _llm_critic_enhance(metrics: dict, agent_results: list) -> list | None:
    """LLC 质疑增强：把全部 Agent 结论交给 LLM 审查，输出必须过结构校验；失败返回 None（跳过）。"""
    if not llm.enabled():
        return None
    payload = [
        {
            "agent_name": r["agent_name"],
            "conclusion": r["conclusion"],
            "recommendation": r["recommendation"],
            "evidence": r["evidence"],
            "data_sources": r["data_sources"],
        }
        for r in agent_results
        if r["agent_name"] != "critic"
    ]
    system = (
        "你是评审专家。以下是光伏清洗决策中各 Agent 的结构化结果。你的职责是发现其中真实的矛盾、"
        "数据误标或逻辑问题。只依据给出的数据判断，不得编造。"
        '输出严格 JSON：{"issues": [{"agent": "Agent 名", "issue": "问题描述", "severity": "high|medium|low"}]}；'
        '无问题则输出 {"issues": []}。'
    )
    text = await llm.chat(system, json.dumps(payload, ensure_ascii=False), temperature=0.1)
    return _parse_llm_issues(text)


def run_critic_agent(metrics: dict, config: dict, prior_results: list, llm_issues: list | None = None) -> dict:
    sources = _sources_of(metrics)
    rule_issues = _rule_critic_checks(metrics, prior_results)
    issues = rule_issues + (llm_issues or [])
    high = [i for i in issues if i.get("severity") == "high"]
    if issues:
        conclusion = (
            f"审查发现 {len(issues)} 项问题（高危 {len(high)} 项）："
            + "；".join(i["issue"] for i in issues[:3])
            + ("；其余略" if len(issues) > 3 else "")
        )
        recommendation = "reject" if high else "flag"
    else:
        conclusion = (
            "审查通过：净收益计算复核一致（容差 2 元）、无结论矛盾、"
            "模拟数据未被误标为实时、抽查单位（mm/m/s/%/元/μg/m³）全部正确。"
        )
        recommendation = "approve"
    confidence = 0.95 if not high else 0.7
    evidence = [_ev("issues_found", len(issues), 0, "项", "above" if issues else "within")]
    return _result(
        "critic",
        conclusion,
        evidence,
        sources,
        assumptions=["规则审查覆盖计算复核、矛盾、误标与单位四类；LLM 增强为可选补充"],
        uncertainties=["LLM 审查不可用时仅规则审查生效，覆盖面有限"],
        recommendation=recommendation,
        confidence=confidence,
        inputs_read={"reviewed_agents": [r["agent_name"] for r in prior_results], "economics_snapshot": {k: (metrics.get("economics") or {}).get(k) for k in ("net_gain", "horizon_revenue", "cleaning_cost", "downtime_loss")}},
        status="ok",
    )


# ---------------------------------------------------------------------------
# 7. Decision Agent（遵守安全否决）
# ---------------------------------------------------------------------------

def run_decision_agent(metrics: dict, config: dict, agent_results: list) -> dict:
    d = metrics["decision"]
    safety = next((r for r in agent_results if r["agent_name"] == "safety"), None)
    critic = next((r for r in agent_results if r["agent_name"] == "critic"), None)
    rule_action = d.get("action", "hold")
    agent_action = rule_action
    veto_applied = False
    if safety and safety.get("recommendation") == "veto":
        veto_applied = True
        veto_type = safety.get("veto_type")
        agent_action = {"weather": "defer", "interval": "hold", "data_quality": "insufficient_data"}.get(veto_type, "hold")
    elif critic and critic.get("recommendation") == "reject":
        # P0-2 修复：Critic 高危 reject 阻止 clean 决策，降级为 hold
        if rule_action == "clean":
            agent_action = "hold"
    if agent_action != rule_action:
        agent_action = agent_action if _CONSERVATIVE_RANK.get(agent_action, 3) >= _CONSERVATIVE_RANK.get(rule_action, 3) else rule_action

    trace = [
        {"factor": "安全否决", "source": "Operation & Safety Agent", "value": safety.get("veto_type") or "无（检查通过）"},
        {"factor": "污损水平", "source": "Soiling Agent", "value": f"估算损失 {metrics['soiling'].get('loss_pct')}%（model_estimate）"},
        {"factor": "经济性", "source": "Economic Agent", "value": f"净收益 {metrics['economics'].get('net_gain')} 元"},
        {"factor": "基础规则决策", "source": "pv_model 确定性计算", "value": rule_action},
        {"factor": "Critic 审查", "source": "Critic Agent", "value": (critic or {}).get("recommendation", "--")},
    ]
    if veto_applied:
        conclusion = (
            f"最终决策：{agent_action}。安全 Agent 否决（{safety.get('veto_type')}）优先于经济收益，"
            f"规则引擎决策为 {rule_action}，按保守原则取 {agent_action}。理由链可追溯（见 decision_trace）。"
        )
    elif agent_action != rule_action:
        conclusion = (
            f"最终决策：{agent_action}。Critic 审查发现高危问题（reject），阻止清洗决策；"
            f"规则引擎决策为 {rule_action}，按保守原则降级为 {agent_action}。理由链可追溯（见 decision_trace）。"
        )
    else:
        conclusion = (
            f"最终决策：{agent_action}。汇总：安全检查通过、污损 {metrics['soiling'].get('loss_pct')}%（估算）、"
            f"净收益 {metrics['economics'].get('net_gain')} 元，与规则引擎决策一致。理由链可追溯（见 decision_trace）。"
        )
    return _result(
        "decision",
        conclusion,
        [_ev("final_action", agent_action, rule_action, "-", "consistent" if agent_action == rule_action else "conservative_override")],
        _sources_of(metrics),
        assumptions=["决策由确定性规则与安全否决合成，本 Agent 不产生新的数值计算"],
        uncertainties=["决策质量受数据质量约束，数据不足时输出 insufficient_data"],
        recommendation=f"final_{agent_action}",
        confidence=0.95 if not veto_applied else 0.9,
        inputs_read={"decision": dict(d), "safety_recommendation": (safety or {}).get("recommendation"), "critic_recommendation": (critic or {}).get("recommendation")},
    ), agent_action, trace, veto_applied


# ---------------------------------------------------------------------------
# 团队编排
# ---------------------------------------------------------------------------

async def run_team(metrics: dict, config: dict) -> dict:
    """按顺序执行 7 个 Agent。返回全部结构化结果与最终裁决。
    LLM 不可用时规则链路独立完成（llm_enhanced=False）。"""
    results: list[dict] = []
    order = []
    for agent_id, fn in (
        ("weather", run_weather_agent),
        ("soiling", run_soiling_agent),
        ("pv_performance", run_pv_performance_agent),
        ("economics", run_economics_agent),
        ("safety", run_safety_agent),
    ):
        raw = fn(metrics, config)
        validated = _validate_result(raw)
        if validated is None:
            validated = _result(
                agent_id,
                "Agent 输出未通过结构校验，已标记 error 并跳过。",
                [], [], ["输出结构不合规"], ["无法评估"],
                "skipped",
                None,
                {},
                status="error",
            )
            validated["agent_name"] = agent_id
        results.append(validated)
        order.append(agent_id)

    llm_issues = None
    llm_enhanced = False
    if llm.enabled():
        try:
            llm_issues = await _llm_critic_enhance(metrics, results)
            llm_enhanced = llm_issues is not None
        except Exception:
            llm_issues = None
            llm_enhanced = False

    critic_result = run_critic_agent(metrics, config, results, llm_issues)
    results.append(critic_result)
    order.append("critic")

    decision_result, final_action, trace, veto_applied = run_decision_agent(metrics, config, results)
    results.append(decision_result)
    order.append("decision")

    rule_issues = [i for i in critic_result.get("inputs_read", {}).keys()]
    high_issues = _rule_critic_checks(metrics, results[:-2]) + [i for i in (llm_issues or []) if i.get("severity") == "high"]

    metrics["agent_execution"] = {
        "agents": results,
        "order": order,
        "critic_issues": _rule_critic_checks(metrics, results[:-2]) + (llm_issues or []),
        "decision_trace": trace,
        "llm_enhanced": llm_enhanced,
        "final_action": final_action,
        "safety_veto_applied": veto_applied,
    }
    return {
        "agent_results": results,
        "order": order,
        "critic_issues": metrics["agent_execution"]["critic_issues"],
        "final_action": final_action,
        "decision_trace": trace,
        "veto_applied": veto_applied,
        "llm_enhanced": llm_enhanced,
        "metrics": metrics,
        "calculation_error": any(i.get("kind") == "calculation_error" for i in high_issues),
        "needs_second_round": any(i.get("kind") == "contradiction" for i in high_issues) is False
        and not veto_applied
        and metrics["decision"].get("action") in ("hold",)
        and (metrics.get("economics") or {}).get("net_gain") is not None,
    }


def to_speak_event(result: dict, stance: str | None = None) -> dict:
    """把 AgentResult 转换为前端已渲染的 agent_speak 兼容事件。"""
    stance_map = {
        "window_suitable": "support",
        "wait_weather_window": "object",
        "significant": "support",
        "not_significant": "object",
        "hold_interval": "object",
        "loss_estimated": "propose",
        "profitable": "support",
        "unprofitable": "object",
        "clear": "support",
        "veto": "object",
        "approve": "support",
        "reject": "object",
        "flag": "propose",
    }
    recommendation = result.get("recommendation", "")
    stance = stance or stance_map.get(recommendation, "propose")
    if recommendation.startswith("final_"):
        stance = "propose"
    meta = AGENT_TEAM_META.get(result["agent_name"], {"name": result.get("role", result["agent_name"]), "goal": ""})
    return {
        "type": "agent_speak",
        "agent": result["agent_name"],
        "agent_name": meta["name"],
        "goal": meta["goal"],
        "stance": stance,
        "message": result.get("conclusion", ""),
        "refs": [f"{e.get('metric')}={e.get('value')}{e.get('unit')}" for e in (result.get("evidence") or [])[:3]],
        "ts": result.get("ts") or _now(),
        "confidence": result.get("confidence"),
        "confidence_type": result.get("confidence_type"),
        "evidence": [
            {"metric": e.get("metric"), "value": e.get("value"), "threshold": e.get("threshold"), "unit": e.get("unit"), "verdict": e.get("verdict"), "margin_ratio": 0.5}
            for e in (result.get("evidence") or [])
        ],
        "execution": {"status": result.get("status"), "recommendation": recommendation, "agent_name": result["agent_name"]},
    }