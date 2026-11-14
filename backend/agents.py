import time

from kb.retriever import retrieve

KB_QUERY = {
    "weather": "风速 降水 高处作业 清洗窗口 天气",
    "soiling": "沙尘 积灰 污损损失率 阈值 局部遮挡",
    "economics": "清洗成本 净收益 回本周期 分区经济性 停机损失",
    "ops": "分区清洗 作业窗口 安全交底 清洗方式 验收",
    "critic": "安全优先 数据不足 决策追溯 多准则冲突 估算实测",
    "arbiter": "分区清洗 经济性对比 冲突处置 安全优先",
}

AGENT_META = {
    "weather": {"name": "气象分析官", "goal": "判断未来窗口是否适合高空作业与清洗"},
    "soiling": {"name": "污损评估官", "goal": "量化沙尘造成的发电损失"},
    "economics": {"name": "收益核算官", "goal": "确认清洗收益覆盖成本"},
    "ops": {"name": "运维调度官", "goal": "给出可执行的清洗窗口与安排"},
    "arbiter": {"name": "仲裁官", "goal": "在收益与成本冲突时给出折中方案"},
    "critic": {"name": "评审主席", "goal": "判断是否执行清洗"},
}


def _confidence(margin_ratio: float) -> float:
    ratio = max(0.0, min(1.0, margin_ratio))
    return round(min(0.99, 0.6 + 0.4 * ratio), 2)


def _ev(metric: str, value, threshold, unit: str, verdict: str, margin: float) -> dict:
    return {
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "unit": unit,
        "verdict": verdict,
        "margin_ratio": round(margin, 2),
    }


def speak(
    agent: str,
    stance: str,
    message: str,
    refs: list | None = None,
    patch: dict | None = None,
    confidence: float | None = None,
    evidence: list | None = None,
) -> dict:
    meta = AGENT_META[agent]
    event = {
        "type": "agent_speak",
        "agent": agent,
        "agent_name": meta["name"],
        "goal": meta["goal"],
        "stance": stance,
        "message": message,
        "refs": refs or [],
        "ts": round(time.time(), 3),
    }
    if confidence is not None:
        event["confidence"] = confidence
    if evidence:
        event["evidence"] = evidence
    kb_refs = retrieve(KB_QUERY.get(agent, ""), applies_to=agent, top_k=2)
    if kb_refs:
        event["kb_refs"] = kb_refs
    if patch:
        event["patch"] = patch
    return event


def _weather_evidence(m: dict, config: dict) -> tuple[list, float, bool]:
    w = m["weather"]
    safety = config["safety"]
    rain = w["rain_next48"]
    wind = w["wind_max"]
    rain_limit = safety["rain_limit_mm"]
    wind_limit = safety["wind_limit_ms"]
    rain_exceed = rain >= rain_limit
    wind_exceed = wind >= wind_limit
    rain_margin = abs(rain - rain_limit) / max(rain_limit, 0.1)
    wind_margin = abs(wind - wind_limit) / max(wind_limit, 0.1)
    evidence = [
        _ev("rain_next48", rain, rain_limit, "mm", "exceed" if rain_exceed else "within", rain_margin),
        _ev("wind_max", wind, wind_limit, "m/s", "exceed" if wind_exceed else "within", wind_margin),
    ]
    blocked = rain_exceed or wind_exceed
    if blocked:
        margin = max(rain_margin if rain_exceed else 0.0, wind_margin if wind_exceed else 0.0)
    else:
        margin = min(rain_margin, wind_margin)
    return evidence, margin, blocked


def weather_opinion(m: dict, config: dict) -> dict:
    w = m["weather"]
    evidence, margin, blocked = _weather_evidence(m, config)
    if blocked:
        return speak(
            "weather",
            "object",
            f"未来 48 小时降水 {w['rain_next48']} mm，最大风速 {w['wind_max']} m/s，不满足清洗窗口，建议延后。",
            refs=[f"{x['date']} {x['irradiance']}kWh/m²" for x in w["days"]],
            confidence=_confidence(margin),
            evidence=evidence,
        )
    return speak(
        "weather",
        "support",
        f"未来 48 小时降水 {w['rain_next48']} mm，最大风速 {w['wind_max']} m/s，辐照均值 {w['avg_irradiance']} kWh/m²，具备作业条件。",
        refs=[f"{x['date']} {x['irradiance']}kWh/m²" for x in w["days"]],
        confidence=_confidence(margin),
        evidence=evidence,
    )


def _soiling_evidence(m: dict, config: dict) -> tuple[list, float, bool]:
    s = m["soiling"]
    threshold = config["soiling"]["low_soiling_threshold_pct"]
    loss = s["loss_pct"]
    below = loss < threshold
    margin = abs(loss - threshold) / max(threshold, 0.1)
    evidence = [
        _ev("soiling_loss", loss, threshold, "%", "below" if below else "above", margin),
        _ev("pm10", s["pm10"], config["soiling"]["pm10_ref"], "µg/m³", "above" if s["pm10"] > config["soiling"]["pm10_ref"] else "within", abs(s["pm10"] - config["soiling"]["pm10_ref"]) / max(config["soiling"]["pm10_ref"], 1)),
    ]
    return evidence, margin, below


def soiling_opinion(m: dict, config: dict) -> dict:
    s = m["soiling"]
    evidence, margin, low = _soiling_evidence(m, config)
    if low:
        return speak(
            "soiling",
            "object",
            f"距上次清洗 {s['days']} 天，PM10 均值 {s['pm10']}，估算污损损失仅 {s['loss_pct']}%，低于显著损失阈值，尚未形成明显发电损失。",
            refs=[f"损失率 {s['loss_pct']}%"],
            patch={"low_soiling": True},
            confidence=_confidence(margin),
            evidence=evidence,
        )
    return speak(
        "soiling",
        "support",
        f"距上次清洗 {s['days']} 天，PM10 均值 {s['pm10']}，估算污损损失 {s['loss_pct']}%，已影响发电效率。",
        refs=[f"损失率 {s['loss_pct']}%", f"PM10 {s['pm10']}"],
        confidence=_confidence(margin),
        evidence=evidence,
    )


def _economics_evidence(m: dict, config: dict) -> tuple[list, float, bool]:
    e = m["economics"]
    net = e["net_gain"]
    base = max(e["horizon_revenue"], e["cleaning_cost"], 1)
    negative = net <= 0
    margin = abs(net) / base
    evidence = [
        _ev("net_gain", net, 0, "元", "below" if negative else "above", margin),
        _ev("payback_days", e["payback_days"], e["horizon_days"], "天", "within" if (e["payback_days"] or 0) <= e["horizon_days"] else "exceed", abs((e["payback_days"] or 0) - e["horizon_days"]) / max(e["horizon_days"], 1)),
    ]
    return evidence, margin, negative


def economics_opinion(m: dict, config: dict) -> dict:
    e = m["economics"]
    evidence, margin, negative = _economics_evidence(m, config)
    if negative:
        return speak(
            "economics",
            "object",
            f"未来 {e['horizon_days']} 天可恢复收益 {e['horizon_revenue']} 元，扣除清洗 {e['cleaning_cost']} 元与停机损失 {e['downtime_loss']} 元后净收益为负，不建议全站清洗。",
            refs=[f"净收益 {e['net_gain']} 元"],
            patch={"negative_net": True},
            confidence=_confidence(margin),
            evidence=evidence,
        )
    return speak(
        "economics",
        "support",
        f"未来 {e['horizon_days']} 天可恢复收益 {e['horizon_revenue']} 元，扣除清洗与停机成本后净收益 {e['net_gain']} 元，回本约 {e['payback_days']} 天。",
        refs=[f"净收益 {e['net_gain']} 元", f"回本 {e['payback_days']} 天"],
        confidence=_confidence(margin),
        evidence=evidence,
    )


def ops_opinion(m: dict, config: dict) -> dict:
    d, w = m["decision"], m["weather"]
    weather_margin = _weather_evidence(m, config)[1]
    econ_margin = _economics_evidence(m, config)[1]
    confidence = _confidence(min(weather_margin, econ_margin))
    if d["action"] == "clean":
        return speak(
            "ops",
            "propose",
            f"建议在 {d['window']} 上午执行{'全站' if d.get('scope') != 'partial' else '分区'}清洗，辐照 {w['best_irradiance']} kWh/m²，风速低于安全阈值，可安排 1 个班组分 4 个方阵作业。",
            refs=[d["window"]],
            confidence=confidence,
            evidence=[_ev("best_irradiance", w["best_irradiance"], w["avg_irradiance"], "kWh/m²", "above" if w["best_irradiance"] >= w["avg_irradiance"] else "within", abs(w["best_irradiance"] - w["avg_irradiance"]) / max(w["avg_irradiance"], 0.1))],
        )
    if d["action"] == "defer":
        return speak(
            "ops",
            "propose",
            f"建议延后至 {w['best_date']}，先做设备与安全交底，待天气窗口满足后再执行。",
            refs=[w["best_date"]],
            confidence=confidence,
            evidence=[_ev("wind_max", w["wind_max"], config["safety"]["wind_limit_ms"], "m/s", "exceed" if w["wind_max"] >= config["safety"]["wind_limit_ms"] else "within", abs(w["wind_max"] - config["safety"]["wind_limit_ms"]) / config["safety"]["wind_limit_ms"])],
        )
    return speak(
        "ops",
        "propose",
        "建议暂不全站清洗，先对污损最重的方阵做一次抽样检测，确认损失率后再决定是否分区清洗。",
        refs=["分区抽样"],
        confidence=confidence,
        evidence=[_ev("soiling_loss", m["soiling"]["loss_pct"], config["soiling"]["low_soiling_threshold_pct"], "%", "below" if m["soiling"]["loss_pct"] < config["soiling"]["low_soiling_threshold_pct"] else "above", abs(m["soiling"]["loss_pct"] - config["soiling"]["low_soiling_threshold_pct"]) / max(config["soiling"]["low_soiling_threshold_pct"], 0.1))],
    )


def critic_judge(m: dict, opinions: list[dict]) -> tuple[bool, dict]:
    blockers = [o for o in opinions if o["stance"] == "object"]
    names = "、".join(o["agent_name"] for o in blockers)
    if blockers:
        conf = round(sum(o.get("confidence", 0.6) for o in blockers) / len(blockers), 2)
        return False, speak(
            "critic",
            "object",
            f"本轮不通过，阻塞项来自：{names}。退回调度官给出替代方案。",
            refs=[o["agent"] for o in blockers],
            confidence=conf,
        )
    d = m["decision"]
    supports = [o for o in opinions if o.get("confidence") is not None]
    conf = round(min(o["confidence"] for o in supports), 2) if supports else 0.6
    return True, speak(
        "critic",
        "support",
        f"方案通过：{d['reason']}。执行窗口 {d['window'] or '暂不执行'}。",
        refs=[d["action"]],
        confidence=conf,
    )


def critic_defer_review(m: dict, config: dict) -> tuple[bool, dict]:
    d = m["decision"]
    w = m["weather"]
    evidence, margin, blocked = _weather_evidence(m, config)
    consistent = blocked == d.get("weather_block") and bool(w.get("best_date"))
    if consistent:
        return True, speak(
            "critic",
            "support",
            f"延后决策经独立复核成立：降水 {w['rain_next48']} mm / 风速 {w['wind_max']} m/s 与安全阈值比对确属阻塞，复评窗口 {w['best_date']}。",
            refs=["延后", w["best_date"]],
            confidence=_confidence(margin),
            evidence=evidence,
        )
    return False, speak(
        "critic",
        "object",
        "延后决策与气象数据不一致，需人工复核后再执行。",
        refs=["数据不一致"],
        confidence=0.6,
        evidence=evidence,
    )


def partial_ratio(m: dict, config: dict) -> float:
    neg = config.get("negotiation") or {}
    low = neg.get("partial_min_ratio", 0.30)
    high = neg.get("partial_max_ratio", 0.70)
    s = m["soiling"]
    max_loss = max(config["soiling"]["max_loss"], 0.01)
    ratio = low + (high - low) * min(1.0, s["loss_ratio"] / max_loss)
    return round(max(low, min(high, ratio)), 2)


def arbitrate(m: dict, config: dict) -> dict:
    ratio = partial_ratio(m, config)
    return speak(
        "arbiter",
        "propose",
        f"全站清洗净收益为 {m['economics']['net_gain']} 元，不成立。按污损程度推导分区比例 {int(ratio * 100)}%（污损损失率 {m['soiling']['loss_pct']}% 越接近上限，清洗比例越高），清洗成本降到 {round(m['economics']['cleaning_cost'] * ratio)} 元，优先恢复高污损方阵。",
        refs=["分区清洗", f"比例 {int(ratio * 100)}%"],
        patch={"partial": True, "cost_ratio": ratio},
        confidence=0.8,
        evidence=[_ev("soiling_loss", m["soiling"]["loss_pct"], config["soiling"]["max_loss"] * 100, "%", "ratio_by_distribution", m["soiling"]["loss_ratio"] / max(config["soiling"]["max_loss"], 0.01))],
    )


def apply_partial(m: dict, config: dict) -> dict:
    e = dict(m["economics"])
    ratio = partial_ratio(m, config)
    recover_ratio = round(ratio + 0.10, 2)
    cost = round(e["cleaning_cost"] * ratio)
    recoverable = e["recoverable_mwh_day"] * recover_ratio
    daily_revenue = e["daily_revenue"] * recover_ratio
    horizon_revenue = daily_revenue * e["horizon_days"]
    downtime = round(e["downtime_loss"] * ratio)
    net = round(horizon_revenue - cost - downtime)
    updated = dict(m)
    updated["economics"] = {
        **e,
        "scope": "partial",
        "scope_ratio": int(ratio * 100),
        "recoverable_mwh_day": round(recoverable, 2),
        "daily_revenue": round(daily_revenue, 0),
        "horizon_revenue": round(horizon_revenue, 0),
        "cleaning_cost": cost,
        "downtime_loss": downtime,
        "net_gain": net,
        "payback_days": round(cost / daily_revenue, 1) if daily_revenue > 0 else None,
    }
    updated["decision"] = {
        **m["decision"],
        "action": "clean" if net > 0 and not m["decision"]["weather_block"] else m["decision"]["action"],
        "scope": "partial",
        "reason": f"全站清洗不经济，按污损分布改为清洗 {int(ratio * 100)}% 方阵，优先恢复高污损区域",
    }
    return updated


def defer_plan(m: dict, config: dict) -> dict:
    updated = dict(m)
    updated["decision"] = {
        **m["decision"],
        "action": "defer",
        "window": m["weather"]["best_date"],
        "reason": "天气窗口不满足，延后至最佳辐照日并保留复评",
    }
    return updated