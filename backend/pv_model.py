import copy


def validate_config(config: dict) -> None:
    errors = []
    site = config.get("site") or {}
    econ = config.get("economics") or {}
    soiling = config.get("soiling") or {}
    safety = config.get("safety") or {}
    if not (0 < site.get("capacity_mw", 0) <= 5000):
        errors.append("capacity_mw 必须在 (0, 5000] 内")
    if site.get("days_since_clean", -1) < 0:
        errors.append("days_since_clean 不能为负")
    if not (0 < econ.get("price_per_kwh", 0) <= 2.0):
        errors.append("price_per_kwh 必须在 (0, 2.0] 内")
    if econ.get("cleaning_cost", -1) < 0:
        errors.append("cleaning_cost 不能为负")
    if not (0 < econ.get("efficiency", 0) <= 1):
        errors.append("efficiency 必须在 (0, 1] 内")
    if not (1 <= econ.get("horizon_days", 0) <= 365):
        errors.append("horizon_days 必须在 [1, 365] 内")
    if not (0 <= econ.get("downtime_hours", -1) <= 48):
        errors.append("downtime_hours 必须在 [0, 48] 内")
    recovery = econ.get("recovery_efficiency", 1.0)
    if not (0 < recovery <= 1):
        errors.append("recovery_efficiency 必须在 (0, 1] 内")
    for part in ("labor_cost", "water_cost", "equipment_cost"):
        value = econ.get(part)
        if value is not None and value < 0:
            errors.append(f"{part} 不能为负")
    if soiling.get("base_rate_per_day", -1) < 0:
        errors.append("base_rate_per_day 不能为负")
    if soiling.get("pm10_factor", 0) < 0:
        errors.append("pm10_factor 不能为负")
    if soiling.get("pm25_factor", 0) < 0:
        errors.append("pm25_factor 不能为负")
    if soiling.get("pm25_ref", 0) < 0:
        errors.append("pm25_ref 不能为负")
    if not (0 < soiling.get("max_loss", 0) <= 1):
        errors.append("max_loss 必须在 (0, 1] 内")
    if soiling.get("tilt_factor", 1.0) <= 0:
        errors.append("tilt_factor 必须为正")
    if soiling.get("rain_clean_threshold_mm", 0) < 0:
        errors.append("rain_clean_threshold_mm 不能为负")
    rain_effect = soiling.get("rain_clean_effect", 0)
    if not (0 <= rain_effect <= 1):
        errors.append("rain_clean_effect 必须在 [0, 1] 内")
    if safety.get("wind_limit_ms", 0) <= 0:
        errors.append("wind_limit_ms 必须为正")
    if safety.get("rain_limit_mm", -1) < 0:
        errors.append("rain_limit_mm 不能为负")
    if errors:
        raise ValueError("参数校验失败：" + "；".join(errors))


def assess_environment(config: dict, context: dict) -> dict:
    """环境风险层：分析 PM10、PM2.5、沙尘、降雨、无有效降雨天数与风速。
    仅使用数据中实际存在的字段；缺失字段在 data_completeness 中如实标注。"""
    air = context.get("air") or {}
    days = (context.get("forecast") or {}).get("days") or []
    soiling_cfg = config["soiling"]
    rain_threshold = soiling_cfg.get("rain_clean_threshold_mm", 2.0)
    natural_clean = any((d.get("rain") or 0) >= rain_threshold for d in days)
    return {
        "pm10": air.get("pm10"),
        "pm2_5": air.get("pm2_5"),
        "dust": air.get("dust"),
        "rain_next72": round(sum(d.get("rain") or 0 for d in days[:3]), 1),
        "natural_clean_expected": natural_clean,
        "no_effective_rain_days": config["site"]["days_since_clean"],
        "wind_max": max((d.get("wind") or 0 for d in days), default=None),
        "data_completeness": {
            "pm10": air.get("pm10") is not None,
            "pm2_5": air.get("pm2_5") is not None,
            "dust": air.get("dust") is not None,
            "forecast_days": len(days),
            "temperature": any(d.get("temp_max") is not None for d in days),
        },
    }


def estimate_soiling(config: dict, context: dict, soiling_override_ratio: float | None = None) -> dict:
    """污损估算层 + 证据层。
    本项目无污损传感器，输出为模型估算（method=model_estimate），不得当作实测污损率展示。
    soiling_override_ratio 仅用于模拟实验室的手动假设，使用后 method=user_assumption，
    并保留 model_loss_pct 供对照，避免把假设值伪装成模型结果。"""
    soiling_cfg = config["soiling"]
    site = config["site"]
    air = context.get("air") or {}
    env = assess_environment(config, context)
    days = site["days_since_clean"]
    pm10 = air.get("pm10", soiling_cfg["pm10_ref"])
    pm25 = air.get("pm2_5")
    pm25_ref = soiling_cfg.get("pm25_ref", 35)
    pm25_extra = 0.0
    if pm25 is not None and pm25 > pm25_ref:
        pm25_extra = (pm25 - pm25_ref) * soiling_cfg.get("pm25_factor", 0.0)
    daily_rate = (
        soiling_cfg["base_rate_per_day"]
        + max(0.0, pm10 - soiling_cfg["pm10_ref"]) * soiling_cfg["pm10_factor"]
        + pm25_extra
    )
    tilt = soiling_cfg.get("tilt_factor", 1.0)
    model_loss = min(soiling_cfg["max_loss"], daily_rate * days * tilt)
    override = None if soiling_override_ratio is None else min(soiling_cfg["max_loss"], max(0.0, soiling_override_ratio))
    loss = model_loss if override is None else override

    drivers = []
    if pm10 is not None and pm10 > soiling_cfg["pm10_ref"]:
        drivers.append(f"PM10={pm10} μg/m³，高于基准 {soiling_cfg['pm10_ref']}")
    if pm25 is not None and pm25 > pm25_ref and soiling_cfg.get("pm25_factor", 0.0) > 0:
        drivers.append(f"PM2.5={pm25} μg/m³，高于演示基准 {pm25_ref}（系数为演示假设）")
    if env["dust"] is not None and env["dust"] > 50:
        drivers.append(f"沙尘浓度 {env['dust']} μg/m³")
    drivers.append(f"距上次清洗 {days} 天（期间无有效清洁降雨记录，以运行天数代理）")
    if env["natural_clean_expected"]:
        drivers.append(f"预报期内有 ≥{soiling_cfg.get('rain_clean_threshold_mm', 2.0)}mm 降雨，存在自然清洁预期")
    if override is not None:
        drivers.append(f"用户手动假设污损损失 {round(override * 100, 1)}%（模型估算为 {round(model_loss * 100, 1)}%）")

    limitations = [
        "无污损传感器实测数据，本值为模型估算，非实测污损率",
        "线性累积假设，未建模沙尘事件突发性与组件类型差异",
        "无有效降雨天数以运行天数代理（无历史降雨观测），可能高估积灰",
    ]
    if tilt == 1.0:
        limitations.append("倾角修正因子=1.0（未启用）：缺乏实测依据，默认不修正")
    if override is not None:
        limitations.append("当前污损值为用户手动假设，仅用于模拟实验室对照，不是模型或实测结果")

    return {
        "daily_rate_pct": round(daily_rate * 100, 3),
        "days": days,
        "pm10": pm10,
        "dust": air.get("dust"),
        "loss_pct": round(loss * 100, 1),
        "loss_ratio": round(loss, 4),
        "model_loss_pct": round(model_loss * 100, 1),
        "model_loss_ratio": round(model_loss, 4),
        "override_applied": override is not None,
        "method": "user_assumption" if override is not None else "model_estimate",
        "drivers": drivers,
        "data_completeness": env["data_completeness"],
        "natural_clean_expected": env["natural_clean_expected"],
        "param_basis": {
            "base_rate_per_day": (config.get("sources") or {}).get("base_rate_per_day", ""),
            "pm10_factor": (config.get("sources") or {}).get("pm10_factor", ""),
        },
        "limitations": limitations,
    }


def _cost_breakdown(econ: dict) -> dict:
    items = {k: econ[k] for k in ("labor_cost", "water_cost", "equipment_cost") if econ.get(k) is not None}
    if items:
        return {"mode": "itemized", "items": items, "total": round(sum(items.values()), 0)}
    return {"mode": "lump_sum", "items": {}, "total": econ.get("cleaning_cost", 0)}


def _check_data_sufficiency(config: dict, context: dict) -> list:
    """数据充分性检查：任何一条不满足即无法给出可信决策。"""
    problems = []
    days = (context.get("forecast") or {}).get("days") or []
    if len(days) < 2:
        problems.append(f"有效预报仅 {len(days)} 天，无法判断 48 小时天气窗口")
    if (context.get("air") or {}).get("pm10") is None:
        problems.append("PM10 缺失，无法估算污损损失")
    if not context.get("theoretical"):
        problems.append("理论发电量基准缺失（PVGIS 不可用），将使用预报辐照降级公式")
    if context.get("quality") == "fallback" and config.get("scenario") == "live":
        problems.append("实时数据获取失败（已降级为样例），不基于模拟数据给出真实决策")
    return problems


def _decide(weather_block: bool, interval_block: bool, economics_ok: bool, site: dict, min_interval: int, net_gain) -> tuple:
    if weather_block:
        return "defer", "未来 48 小时有降水或大风，清洗后易再次污染或存在高空作业风险，建议等待天气窗口"
    if interval_block:
        return "hold", f"距上次清洗仅 {site['days_since_clean']} 天，低于最小清洗间隔 {min_interval} 天，重复清洗会增加成本并提高组件划伤风险"
    if not economics_ok:
        return "hold", f"评估期内净收益为{'负' if net_gain is not None and net_gain < 0 else '零'}，清洗不经济，建议继续监测"
    return "clean", "天气窗口满足、满足最小清洗间隔且净收益为正"


def sensitivity_analysis(config: dict, context: dict, base_action: str, base_net_gain, soiling_override_ratio: float | None = None) -> dict:
    """单因素确定性敏感性分析：每次仅改变一个参数重算净收益与决策。
    本方法为确定性扰动，非概率模拟，无分布假设，不输出任何编造的置信概率。"""
    econ = config["economics"]
    soiling_cfg = config["soiling"]

    def bump_price(factor):
        def apply(c):
            c["economics"]["price_per_kwh"] = round(econ["price_per_kwh"] * factor, 4)
        return apply

    def bump_cost(factor):
        def apply(c):
            c["economics"]["cleaning_cost"] = round(econ["cleaning_cost"] * factor, 0)
            for k in ("labor_cost", "water_cost", "equipment_cost"):
                if c["economics"].get(k) is not None:
                    c["economics"][k] = round(c["economics"][k] * factor, 0)
        return apply

    def bump_soiling(factor):
        def apply(c):
            c["soiling"]["base_rate_per_day"] = round(soiling_cfg["base_rate_per_day"] * factor, 6)
            c["soiling"]["pm10_factor"] = round(soiling_cfg["pm10_factor"] * factor, 8)
        return apply

    def set_recovery(value):
        def apply(c):
            c["economics"]["recovery_efficiency"] = value
        return apply

    def bump_generation(factor):
        def apply(c):
            c["economics"]["efficiency"] = round(econ["efficiency"] * factor, 4)
        return apply

    def set_rain_effect(value):
        def apply(c):
            c["soiling"]["rain_clean_effect"] = value
        return apply

    scenarios = [
        ("电价", "+20%", bump_price(1.2)),
        ("电价", "-20%", bump_price(0.8)),
        ("清洗成本", "+20%", bump_cost(1.2)),
        ("清洗成本", "-20%", bump_cost(0.8)),
        ("污损速率", "+20%", bump_soiling(1.2)),
        ("污损速率", "-20%", bump_soiling(0.8)),
        ("恢复效率", "1.00（完全恢复）", set_recovery(1.0)),
        ("恢复效率", "0.90", set_recovery(0.9)),
        ("发电水平", "+20%", bump_generation(1.2)),
        ("发电水平", "-20%", bump_generation(0.8)),
        ("降雨自然清洁", "效果=0（不折减）", set_rain_effect(0.0)),
        ("降雨自然清洁", "效果=0.6", set_rain_effect(0.6)),
    ]
    results = []
    for name, change, apply in scenarios:
        cfg2 = copy.deepcopy(config)
        apply(cfg2)
        try:
            m2 = compute_metrics(cfg2, context, include_sensitivity=False, soiling_override_ratio=soiling_override_ratio)
            action2 = m2["decision"]["action"]
            results.append(
                {
                    "param": name,
                    "change": change,
                    "net_gain": m2["economics"]["net_gain"],
                    "action": action2,
                    "flips_decision": action2 != base_action,
                }
            )
        except ValueError as e:
            results.append({"param": name, "change": change, "error": str(e)[:80]})
    return {
        "method": "one_factor_deterministic",
        "note": "单因素确定性敏感性分析：每次仅扰动一个参数并完整重算；非蒙特卡洛，无概率分布假设。",
        "base_action": base_action,
        "base_net_gain": base_net_gain,
        "scenarios": results,
    }


def compute_metrics(config: dict, context: dict, include_sensitivity: bool = True, soiling_override_ratio: float | None = None) -> dict:
    validate_config(config)
    site = config["site"]
    econ = config["economics"]
    safety = config["safety"]
    soiling_cfg = config["soiling"]
    forecast = context["forecast"]
    days = forecast.get("days") or []
    air = context.get("air") or {}
    sources = config.get("sources") or {}

    insufficient = _check_data_sufficiency(config, context)

    if insufficient and (len(days) < 2 or air.get("pm10") is None or (context.get("quality") == "fallback" and config.get("scenario") == "live")):
        return {
            "site": site,
            "soiling": {
                "loss_pct": None, "loss_ratio": None, "days": site["days_since_clean"],
                "pm10": air.get("pm10"), "dust": air.get("dust"), "method": "model_estimate",
                "drivers": [], "data_completeness": assess_environment(config, context)["data_completeness"],
                "natural_clean_expected": False, "param_basis": {}, "limitations": ["数据不足，模型未执行"],
            },
            "weather": {"avg_irradiance": None, "rain_next48": None, "wind_max": None, "best_date": None,
                        "best_irradiance": None, "days": days, "source": forecast.get("source"),
                        "fetched_at": forecast.get("fetched_at"), "quality": forecast.get("quality")},
            "economics": {"theory_mwh_day": None, "theoretical_source": None, "pvgis": None,
                          "recoverable_mwh_day": None, "daily_revenue": None, "horizon_days": econ.get("horizon_days"),
                          "horizon_revenue": None, "cleaning_cost": econ.get("cleaning_cost"), "downtime_loss": None,
                          "net_gain": None, "payback_days": None, "price_per_kwh": econ.get("price_per_kwh"),
                          "recovery_efficiency": None, "natural_clean_discount": None, "cost_breakdown": _cost_breakdown(econ)},
            "decision": {
                "action": "insufficient_data",
                "reason": "；".join(insufficient),
                "window": None, "weather_block": None, "interval_block": None,
                "min_clean_interval_days": soiling_cfg.get("min_clean_interval_days", 14),
                "economics_ok": None, "data_insufficient": insufficient,
            },
            "data_quality": {
                "forecast_source": forecast.get("source"), "air_source": air.get("source"),
                "forecast_quality": forecast.get("quality"), "air_quality": air.get("quality"),
                "overall_quality": context.get("quality"), "fetched_at": context.get("fetched_at"),
                "data_sources": context.get("data_source_records", []),
                "note": "数据不足，未执行决策计算。",
            },
            "formulas": {"param_sources": sources},
            "sensitivity": None,
        }

    soiling = estimate_soiling(config, context, soiling_override_ratio=soiling_override_ratio)

    theoretical = context.get("theoretical")
    if theoretical and theoretical.get("E_d"):
        theory_mwh_day = site["capacity_mw"] * theoretical["E_d"]
        theoretical_source = "pvgis"
    else:
        avg_irradiance = sum(d["irradiance"] for d in days) / len(days)
        theory_mwh_day = site["capacity_mw"] * avg_irradiance * econ["efficiency"]
        theoretical_source = "formula"
    avg_irradiance = sum(d["irradiance"] for d in days) / len(days)

    recovery = econ.get("recovery_efficiency", 1.0)
    rain_effect = soiling_cfg.get("rain_clean_effect", 0.0) if soiling["natural_clean_expected"] else 0.0
    natural_clean_discount = round(1 - rain_effect, 3)

    effective_loss = soiling["loss_ratio"] * recovery * natural_clean_discount
    recoverable_mwh_day = theory_mwh_day * effective_loss
    recoverable_kwh_day = recoverable_mwh_day * 1000
    daily_revenue = recoverable_kwh_day * econ["price_per_kwh"]

    horizon = econ["horizon_days"]
    horizon_revenue = daily_revenue * horizon
    breakdown = _cost_breakdown(econ)
    cleaning_total = breakdown["total"]
    downtime_loss = (theory_mwh_day / 24) * econ["downtime_hours"] * econ["price_per_kwh"] * 1000
    net_gain = horizon_revenue - cleaning_total - downtime_loss
    payback = cleaning_total / daily_revenue if daily_revenue > 0 else None

    rain_next48 = sum(d["rain"] for d in days[:2])
    wind_max = max(d["wind"] for d in days)
    best = max(days, key=lambda d: d["irradiance"] - d["wind"] * 0.05 - d["rain"] * 2)

    weather_block = rain_next48 >= safety["rain_limit_mm"] or wind_max >= safety["wind_limit_ms"]
    min_interval = soiling_cfg.get("min_clean_interval_days", 14)
    interval_block = site["days_since_clean"] < min_interval
    economics_ok = net_gain > 0

    action, reason = _decide(weather_block, interval_block, economics_ok, site, min_interval, net_gain)

    metrics = {
        "site": site,
        "soiling": soiling,
        "weather": {
            "avg_irradiance": round(avg_irradiance, 2),
            "rain_next48": round(rain_next48, 1),
            "wind_max": round(wind_max, 1),
            "best_date": best["date"],
            "best_irradiance": best["irradiance"],
            "days": days,
            "source": forecast.get("source"),
            "fetched_at": forecast.get("fetched_at"),
            "quality": forecast.get("quality"),
        },
        "economics": {
            "theory_mwh_day": round(theory_mwh_day, 1),
            "theoretical_source": theoretical_source,
            "pvgis": {
                "E_d": theoretical.get("E_d"),
                "month": theoretical.get("month"),
                "radiation_db": theoretical.get("radiation_db"),
                "year_min": theoretical.get("year_min"),
                "year_max": theoretical.get("year_max"),
                "cached": theoretical.get("cached", False),
            }
            if theoretical
            else None,
            "recoverable_mwh_day": round(recoverable_mwh_day, 2),
            "daily_revenue": round(daily_revenue, 0),
            "horizon_days": horizon,
            "horizon_revenue": round(horizon_revenue, 0),
            "cleaning_cost": cleaning_total,
            "downtime_loss": round(downtime_loss, 0),
            "net_gain": round(net_gain, 0),
            "payback_days": round(payback, 1) if payback else None,
            "price_per_kwh": econ["price_per_kwh"],
            "recovery_efficiency": recovery,
            "natural_clean_discount": natural_clean_discount,
            "cost_breakdown": breakdown,
        },
        "decision": {
            "action": action,
            "reason": reason,
            "window": best["date"] if action == "clean" else None,
            "weather_block": weather_block,
            "interval_block": interval_block,
            "min_clean_interval_days": min_interval,
            "economics_ok": economics_ok,
        },
        "data_quality": {
            "forecast_source": forecast.get("source"),
            "air_source": air.get("source"),
            "forecast_quality": forecast.get("quality"),
            "air_quality": air.get("quality"),
            "overall_quality": context.get("quality"),
            "fetched_at": context.get("fetched_at"),
            "data_sources": context.get("data_source_records", []),
            "note": "辐照、降水、风速来自公开气象接口；收益为估算模型，参数可在配置中调整。",
        },
        "formulas": {
            "theory": "理论日发电量(MWh) = 装机容量(MW) × E_d(kWh/kWp)，E_d 来自 PVGIS 历史气候；降级时 = 装机容量 × 日辐照(kWh/m²，近似峰值日照小时) × 系统效率",
            "soiling": "污损损失率 = min(上限, (基础速率 + max(0, PM10 − 基准) × 系数) × 运行天数 × 倾角因子)；无传感器，为模型估算",
            "effective_loss": "有效可恢复损失 = 污损损失率 × 清洗恢复效率 × (1 − 降雨自然清洁折减)",
            "revenue": "日增量收益(元) = 理论日发电量 × 有效可恢复损失 × 1000 × 电价；评估期内统一按此口径，不重复计收益",
            "net": "净收益(元) = 日增量收益 × 评估天数 − 清洗总成本(人工+用水+设备或包干) − 停机损失",
            "downtime": "停机损失(元) = 理论日发电量 ÷ 24 × 停机小时 × 电价 × 1000",
            "param_sources": sources,
        },
    }

    if include_sensitivity:
        metrics["sensitivity"] = sensitivity_analysis(config, context, action, round(net_gain, 0), soiling_override_ratio=soiling_override_ratio)
    else:
        metrics["sensitivity"] = None

    return metrics