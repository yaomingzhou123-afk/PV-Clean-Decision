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
    if soiling.get("base_rate_per_day", -1) < 0:
        errors.append("base_rate_per_day 不能为负")
    if not (0 < soiling.get("max_loss", 0) <= 1):
        errors.append("max_loss 必须在 (0, 1] 内")
    if safety.get("wind_limit_ms", 0) <= 0:
        errors.append("wind_limit_ms 必须为正")
    if safety.get("rain_limit_mm", -1) < 0:
        errors.append("rain_limit_mm 不能为负")
    if errors:
        raise ValueError("参数校验失败：" + "；".join(errors))


def estimate_soiling(config: dict, air: dict) -> dict:
    soiling = config["soiling"]
    days = config["site"]["days_since_clean"]
    pm10 = air.get("pm10", soiling["pm10_ref"])
    daily_rate = soiling["base_rate_per_day"] + max(0.0, pm10 - soiling["pm10_ref"]) * soiling["pm10_factor"]
    loss = min(soiling["max_loss"], daily_rate * days)
    return {
        "daily_rate_pct": round(daily_rate * 100, 3),
        "days": days,
        "pm10": pm10,
        "dust": air.get("dust"),
        "loss_pct": round(loss * 100, 1),
        "loss_ratio": round(loss, 4),
    }


def compute_metrics(config: dict, context: dict) -> dict:
    validate_config(config)
    site = config["site"]
    econ = config["economics"]
    safety = config["safety"]
    forecast = context["forecast"]
    days = forecast.get("days") or []
    if not days:
        raise ValueError("气象数据为空，无法完成决策计算")
    soiling = estimate_soiling(config, context["air"])

    theoretical = context.get("theoretical")
    if theoretical and theoretical.get("E_d"):
        theory_mwh_day = site["capacity_mw"] * theoretical["E_d"]
        theoretical_source = "pvgis"
    else:
        avg_irradiance = sum(d["irradiance"] for d in days) / len(days)
        theory_mwh_day = site["capacity_mw"] * avg_irradiance * econ["efficiency"]
        theoretical_source = "formula"
    avg_irradiance = sum(d["irradiance"] for d in days) / len(days)

    recoverable_mwh_day = theory_mwh_day * soiling["loss_ratio"]
    recoverable_kwh_day = recoverable_mwh_day * 1000
    daily_revenue = recoverable_kwh_day * econ["price_per_kwh"]

    horizon = econ["horizon_days"]
    horizon_revenue = daily_revenue * horizon
    downtime_loss = (theory_mwh_day / 24) * econ["downtime_hours"] * econ["price_per_kwh"] * 1000
    net_gain = horizon_revenue - econ["cleaning_cost"] - downtime_loss
    payback = econ["cleaning_cost"] / daily_revenue if daily_revenue > 0 else None

    rain_next48 = sum(d["rain"] for d in days[:2])
    wind_max = max(d["wind"] for d in days)
    best = max(days, key=lambda d: d["irradiance"] - d["wind"] * 0.05 - d["rain"] * 2)

    weather_block = rain_next48 >= safety["rain_limit_mm"] or wind_max >= safety["wind_limit_ms"]
    min_interval = config["soiling"].get("min_clean_interval_days", 14)
    interval_block = site["days_since_clean"] < min_interval
    economics_ok = net_gain > 0

    if weather_block:
        action = "defer"
        reason = "未来 48 小时有降水或大风，清洗后易再次污染或存在高空作业风险"
    elif interval_block:
        action = "hold"
        reason = f"距上次清洗仅 {site['days_since_clean']} 天，低于行业最小清洗间隔 {min_interval} 天，重复清洗会增加成本并提高组件划伤风险"
    elif not economics_ok:
        action = "hold"
        reason = "未来收益不足以覆盖清洗与停机成本，建议继续监测"
    else:
        action = "clean"
        reason = "天气窗口满足、满足最小清洗间隔且净收益为正"

    sources = config.get("sources") or {}
    return {
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
            "cleaning_cost": econ["cleaning_cost"],
            "downtime_loss": round(downtime_loss, 0),
            "net_gain": round(net_gain, 0),
            "payback_days": round(payback, 1) if payback else None,
            "price_per_kwh": econ["price_per_kwh"],
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
            "air_source": context["air"].get("source"),
            "forecast_quality": forecast.get("quality"),
            "air_quality": context["air"].get("quality"),
            "overall_quality": context.get("quality"),
            "fetched_at": context.get("fetched_at"),
            "data_sources": context.get("data_source_records", []),
            "note": "辐照、降水、风速来自公开气象接口；收益为估算模型，参数可在配置中调整。",
        },
        "formulas": {
            "theory": "理论日发电量(MWh) = 装机容量(MW) × E_d(kWh/kWp)，E_d 来自 PVGIS；降级时 = 装机容量 × 日辐照(kWh/m²，近似峰值日照小时) × 系统效率",
            "soiling": "污损损失率 = min(上限, (基础速率 + max(0, PM10 − 基准) × 系数) × 运行天数)",
            "revenue": "日恢复收益(元) = 理论日发电量 × 污损损失率 × 1000 × 电价",
            "net": "净收益(元) = 日恢复收益 × 评估天数 − 清洗成本 − 停机损失",
            "downtime": "停机损失(元) = 理论日发电量 ÷ 24 × 停机小时 × 电价 × 1000",
            "param_sources": sources,
        },
    }