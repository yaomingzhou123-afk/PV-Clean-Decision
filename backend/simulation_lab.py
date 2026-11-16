"""V3.0 第六阶段：清洗决策模拟实验室。

设计约束：
1. 所有结果均为模拟计算结果，使用用户输入或明确标注的示例假设，不代表真实电站运行数据。
2. 污损/发电/经济计算复用 pv_model 的同一套确定性公式；本模块只负责参数装配、
   场景对照和展示所需的结构化摘要。
3. 三种策略使用相同输入和相同评价周期；没有真实历史数据，因此只能称为模型模拟比较，
   不得称为真实回测或真实收益。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from data_sources.models import now_iso
from pv_model import compute_metrics

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "data" / "pv_config.json"

DISCLAIMER = "模拟计算结果：基于用户输入或示例假设，不代表真实电站运行数据，也不构成真实回测或收益承诺。"

SCENARIO_NOTE = "示例假设：仅用于演示参数变化，不代表真实电站，也不代表行业标准。"


PARAM_SPECS = [
    {
        "key": "pm10",
        "label": "PM10",
        "unit": "μg/m³",
        "min": 0,
        "max": 2000,
        "step": 1,
        "default": 80,
        "description": "颗粒物浓度输入，用于污损速率增量；不是实测传感器数据。默认取基准值以展示参数变化。",
        "basis": "示例输入，不代表实测或行业标准。",
    },
    {
        "key": "pm2_5",
        "label": "PM2.5",
        "unit": "μg/m³",
        "min": 0,
        "max": 1000,
        "step": 1,
        "default": 24,
        "description": "细颗粒物浓度输入；高于演示基准 35 μg/m³ 时按演示系数增加污损速率。",
        "basis": "示例输入，不代表实测或行业标准。",
    },
    {
        "key": "dry_days",
        "label": "连续无有效降雨天数",
        "unit": "天",
        "min": 0,
        "max": 365,
        "step": 1,
        "default": 20,
        "description": "作为积灰累积天数代理；项目没有历史降雨观测，因此该值可能与真实现场不同。",
        "basis": "示例假设，不代表真实气象观测。",
    },
    {
        "key": "soiling_override_pct",
        "label": "污损损失手动假设",
        "unit": "%",
        "min": 0,
        "max": 30,
        "step": 0.5,
        "default": None,
        "allow_empty": True,
        "description": "留空则使用模型估算；填写后作为手动假设值。超过模型上限 15% 时按 15% 计算并提示。",
        "basis": "可选假设值，不是实测污损率。",
    },
    {
        "key": "capacity_mw",
        "label": "装机容量",
        "unit": "MW",
        "min": 0.5,
        "max": 5000,
        "step": 0.5,
        "default": 20,
        "description": "电站装机容量；用于理论发电量、停机损失和收益计算。",
        "basis": "示例输入，按目标电站实际值替换。",
    },
    {
        "key": "tilt_angle_deg",
        "label": "组件倾角",
        "unit": "°",
        "min": 0,
        "max": 60,
        "step": 1,
        "default": 35,
        "description": "倾角对积灰和发电量均使用演示映射：35° 为参考，偏离越大按线性折减；没有实测依据，仅用于观察趋势。",
        "basis": "演示假设，不得作为工程结论或行业标准。",
    },
    {
        "key": "price_per_kwh",
        "label": "上网电价",
        "unit": "元/kWh",
        "min": 0.05,
        "max": 2.0,
        "step": 0.01,
        "default": 0.25,
        "description": "用于把发电量转换为收益；不是实时电力市场价格。",
        "basis": "项目配置默认值，按实际合同/政策替换。",
    },
    {
        "key": "labor_cost",
        "label": "清洗人工成本",
        "unit": "元/次",
        "min": 0,
        "max": 100000,
        "step": 100,
        "default": 2000,
        "description": "单次清洗的人工成本分项；清洗总成本 = 人工 + 用水 + 设备。",
        "basis": "示例假设，按实际合同价替换。",
    },
    {
        "key": "water_cost",
        "label": "清洗用水成本",
        "unit": "元/次",
        "min": 0,
        "max": 100000,
        "step": 100,
        "default": 1000,
        "description": "单次清洗的用水成本分项。",
        "basis": "示例假设，按实际合同价替换。",
    },
    {
        "key": "equipment_cost",
        "label": "设备及其他清洗成本",
        "unit": "元/次",
        "min": 0,
        "max": 100000,
        "step": 100,
        "default": 1000,
        "description": "设备、运输、耗材等其他单次成本分项。",
        "basis": "示例假设，按实际合同价替换。",
    },
    {
        "key": "expected_rain_mm",
        "label": "预计未来降雨",
        "unit": "mm",
        "min": 0,
        "max": 200,
        "step": 0.5,
        "default": 0,
        "description": "未来 24–48 小时降雨假设；用于天气风险判断和自然清洁折减。",
        "basis": "示例假设，不是气象预报实测值。",
    },
    {
        "key": "wind_speed_ms",
        "label": "风速",
        "unit": "m/s",
        "min": 0,
        "max": 60,
        "step": 0.5,
        "default": 9,
        "description": "作业窗口风速假设；与项目配置的安全阈值比较。",
        "basis": "示例假设；安全阈值来自项目配置，不是行业统一标准。",
    },
    {
        "key": "recovery_efficiency",
        "label": "清洗后恢复效率",
        "unit": "比例",
        "min": 0.5,
        "max": 1.0,
        "step": 0.01,
        "default": 0.95,
        "description": "清洗后可恢复的污损损失比例；1.0 表示完全恢复。属于经验假设。",
        "basis": "经验假设，待实测校准。",
    },
    {
        "key": "avg_irradiance_kwh_m2_day",
        "label": "日辐照（示例）",
        "unit": "kWh/m²/日",
        "min": 0.5,
        "max": 10,
        "step": 0.1,
        "default": 5.8,
        "description": "用于降级公式的理论发电量估算；不是实时辐照或 PVGIS 历史值。",
        "basis": "示例假设，仅用于模拟实验室。",
    },
    {
        "key": "horizon_days",
        "label": "评价周期",
        "unit": "天",
        "min": 7,
        "max": 90,
        "step": 1,
        "default": 30,
        "description": "三种策略使用同一评价周期；收益和成本都按该周期汇总。",
        "basis": "示例假设，可按演示需要调整。",
    },
    {
        "key": "fixed_cycle_days",
        "label": "固定周期策略间隔",
        "unit": "天",
        "min": 7,
        "max": 90,
        "step": 1,
        "default": 30,
        "description": "固定周期策略的清洗间隔；短于 14 天时会提示与最小清洗间隔冲突。",
        "basis": "示例假设，不是行业推荐周期。",
    },
    {
        "key": "soiling_threshold_pct",
        "label": "污损阈值策略阈值",
        "unit": "%",
        "min": 1,
        "max": 15,
        "step": 0.5,
        "default": 5,
        "description": "污损阈值策略和联合策略的触发阈值；属于演示假设。",
        "basis": "示例假设，不代表行业统一阈值。",
    },
]


DEFAULTS = {spec["key"]: spec["default"] for spec in PARAM_SPECS}


DEMO_SCENARIOS = [
    {
        "id": "A",
        "name": "示例 A · 高粉尘、长期无雨",
        "note": SCENARIO_NOTE,
        "params": {
            **DEFAULTS,
            "pm10": 300,
            "pm2_5": 80,
            "dry_days": 60,
            "expected_rain_mm": 0,
            "wind_speed_ms": 8,
        },
    },
    {
        "id": "B",
        "name": "示例 B · 污损较高但未来即将降雨",
        "note": SCENARIO_NOTE,
        "params": {
            **DEFAULTS,
            "pm10": 220,
            "pm2_5": 55,
            "dry_days": 45,
            "expected_rain_mm": 8,
            "wind_speed_ms": 9,
        },
    },
    {
        "id": "C",
        "name": "示例 C · 清洗成本较高且污损较低",
        "note": SCENARIO_NOTE,
        "params": {
            **DEFAULTS,
            "pm10": 85,
            "pm2_5": 20,
            "dry_days": 5,
            "expected_rain_mm": 0,
            "wind_speed_ms": 8,
            "labor_cost": 20000,
            "water_cost": 10000,
            "equipment_cost": 30000,
        },
    },
]


def _base_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _thresholds() -> dict:
    config = _base_config()
    return {
        "wind_limit_ms": config["safety"]["wind_limit_ms"],
        "rain_limit_mm": config["safety"]["rain_limit_mm"],
        "min_clean_interval_days": config["soiling"]["min_clean_interval_days"],
        "max_loss_pct": round(config["soiling"]["max_loss"] * 100, 1),
        "rain_clean_threshold_mm": config["soiling"]["rain_clean_threshold_mm"],
        "rain_clean_effect": config["soiling"]["rain_clean_effect"],
    }


def _tilt_factor(tilt_angle_deg: float) -> float:
    """演示用倾角映射：35° 为参考值，倾角越高积灰折减越多。

    这不是实测模型，只用于让参数影响可见；文档和界面都标注为演示假设。
    """
    factor = 1.0 - 0.15 * (float(tilt_angle_deg) - 35.0) / 25.0
    return round(max(0.85, min(1.15, factor)), 4)


def _tilt_energy_factor(tilt_angle_deg: float) -> float:
    """演示用倾角-发电量映射：35° 为参考值，偏离越大按线性折减。

    这不是实测模型，仅用于展示倾角参数对结果的影响；不得作为工程设计依据。
    """
    factor = 1.0 - 0.25 * abs(float(tilt_angle_deg) - 35.0) / 35.0
    return round(max(0.75, factor), 4)


def _normalize(payload: dict | None) -> dict:
    payload = payload or {}
    params = copy.deepcopy(DEFAULTS)
    for spec in PARAM_SPECS:
        key = spec["key"]
        if key not in payload:
            continue
        value = payload[key]
        if value is None and spec.get("allow_empty"):
            params[key] = None
            continue
        if value is None:
            raise ValueError(f"{spec['label']} 不能为空")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{spec['label']} 必须是数字")
        if not (spec["min"] <= value <= spec["max"]):
            raise ValueError(
                f"{spec['label']} 必须在 {spec['min']}–{spec['max']} {spec['unit']} 之间"
            )
        params[key] = value
    if params["soiling_override_pct"] is not None:
        params["soiling_override_pct"] = min(30.0, max(0.0, float(params["soiling_override_pct"])))
    return params


def _build_config(params: dict) -> dict:
    config = _base_config()
    total_cost = float(params["labor_cost"]) + float(params["water_cost"]) + float(params["equipment_cost"])
    config["site"]["capacity_mw"] = float(params["capacity_mw"])
    config["site"]["days_since_clean"] = int(round(params["dry_days"]))
    config["economics"]["price_per_kwh"] = float(params["price_per_kwh"])
    config["economics"]["cleaning_cost"] = total_cost
    config["economics"]["labor_cost"] = float(params["labor_cost"])
    config["economics"]["water_cost"] = float(params["water_cost"])
    config["economics"]["equipment_cost"] = float(params["equipment_cost"])
    config["economics"]["recovery_efficiency"] = float(params["recovery_efficiency"])
    config["economics"]["horizon_days"] = int(round(params["horizon_days"]))
    config["soiling"]["tilt_factor"] = _tilt_factor(params["tilt_angle_deg"])
    config["soiling"]["pm25_ref"] = 35.0
    config["soiling"]["pm25_factor"] = 0.00005
    config["soiling"]["low_soiling_threshold_pct"] = float(params["soiling_threshold_pct"])
    config["scenario"] = "simulation"
    return config


def _build_context(params: dict) -> dict:
    stamp = now_iso()
    irradiance = float(params["avg_irradiance_kwh_m2_day"]) * _tilt_energy_factor(params["tilt_angle_deg"])
    rain = float(params["expected_rain_mm"])
    wind = float(params["wind_speed_ms"])
    days = [
        {
            "date": f"模拟 D{i + 1}",
            "irradiance": irradiance,
            "rain": rain if i == 0 else 0.0,
            "wind": wind,
            "cloud": 0,
            "temp_max": None,
            "temp_min": None,
        }
        for i in range(3)
    ]
    air = {
        "pm10": float(params["pm10"]),
        "pm2_5": float(params["pm2_5"]),
        "dust": None,
        "source": "simulation-lab",
        "quality": "simulation",
        "fetched_at": stamp,
    }
    forecast = {
        "days": days,
        "source": "simulation-lab",
        "quality": "simulation",
        "fetched_at": stamp,
    }
    record = {
        "source": "simulation-lab",
        "data_type": "user_input_scenario",
        "data_kind": "simulation",
        "latitude": None,
        "longitude": None,
        "value": {
            "pm10": params["pm10"],
            "pm2_5": params["pm2_5"],
            "dry_days": params["dry_days"],
            "capacity_mw": params["capacity_mw"],
            "tilt_angle_deg": params["tilt_angle_deg"],
            "price_per_kwh": params["price_per_kwh"],
            "labor_cost": params["labor_cost"],
            "water_cost": params["water_cost"],
            "equipment_cost": params["equipment_cost"],
            "expected_rain_mm": params["expected_rain_mm"],
            "wind_speed_ms": params["wind_speed_ms"],
            "recovery_efficiency": params["recovery_efficiency"],
        },
        "unit": {
            "pm10": "μg/m³",
            "pm2_5": "μg/m³",
            "dry_days": "天",
            "capacity_mw": "MW",
            "tilt_angle_deg": "°",
            "price_per_kwh": "元/kWh",
            "labor_cost": "元/次",
            "water_cost": "元/次",
            "equipment_cost": "元/次",
            "expected_rain_mm": "mm",
            "wind_speed_ms": "m/s",
            "recovery_efficiency": "比例",
        },
        "valid_time": "用户输入假设",
        "fetched_at": stamp,
        "status": "ok",
        "is_simulated": True,
        "is_cached": False,
        "error_message": None,
    }
    return {
        "forecast": forecast,
        "air": air,
        "theoretical": None,
        "quality": "simulation",
        "fetched_at": stamp,
        "data_source_records": [record],
    }


def _initial_loss(config: dict, context: dict, params: dict) -> tuple[float, float]:
    soiling = config["soiling"]
    pm10 = float(params["pm10"])
    pm25 = float(params["pm2_5"])
    pm25_extra = max(0.0, pm25 - soiling.get("pm25_ref", 35)) * soiling.get("pm25_factor", 0.0)
    daily_rate = (
        soiling["base_rate_per_day"]
        + max(0.0, pm10 - soiling["pm10_ref"]) * soiling["pm10_factor"]
        + pm25_extra
    )
    tilt = soiling["tilt_factor"]
    model_loss = min(soiling["max_loss"], daily_rate * int(round(params["dry_days"])) * tilt)
    if params["soiling_override_pct"] is None:
        return model_loss, daily_rate * tilt
    override = min(soiling["max_loss"], max(0.0, float(params["soiling_override_pct"]) / 100.0))
    return override, daily_rate * tilt


def _summary(metrics: dict, params: dict, warnings: list[str]) -> dict:
    economics = metrics["economics"]
    soiling = metrics["soiling"]
    decision = metrics["decision"]
    weather = metrics["weather"]
    action = decision["action"]
    labels = {"clean": "建议清洗", "defer": "建议延后", "hold": "暂不清洗", "insufficient_data": "数据不足"}
    return {
        "soiling_risk": {
            "loss_pct": soiling.get("loss_pct"),
            "model_loss_pct": soiling.get("model_loss_pct"),
            "override_applied": soiling.get("override_applied", False),
            "daily_rate_pct": soiling.get("daily_rate_pct"),
            "method": soiling.get("method"),
        },
        "energy_loss": {
            "recoverable_mwh_day": economics.get("recoverable_mwh_day"),
            "daily_revenue": economics.get("daily_revenue"),
            "theory_mwh_day": economics.get("theory_mwh_day"),
        },
        "cost": {
            "cleaning_total": economics.get("cleaning_cost"),
            "downtime_loss": economics.get("downtime_loss"),
            "cost_breakdown": economics.get("cost_breakdown"),
        },
        "revenue": {
            "horizon_revenue": economics.get("horizon_revenue"),
            "horizon_days": economics.get("horizon_days"),
        },
        "net_gain": economics.get("net_gain"),
        "payback_days": economics.get("payback_days"),
        "weather": {
            "rain_next48": weather.get("rain_next48"),
            "wind_max": weather.get("wind_max"),
            "rain_limit_mm": _thresholds()["rain_limit_mm"],
            "wind_limit_ms": _thresholds()["wind_limit_ms"],
            "blocked": bool(decision.get("weather_block")),
        },
        "decision": {
            "action": action,
            "label": labels.get(action, action),
            "reason": decision.get("reason"),
            "window": decision.get("window"),
            "economics_ok": decision.get("economics_ok"),
        },
        "warnings": warnings,
    }


def _warnings(metrics: dict, params: dict, config: dict) -> list[str]:
    warnings: list[str] = []
    soiling = metrics["soiling"]
    economics = metrics["economics"]
    if params["soiling_override_pct"] is not None and params["soiling_override_pct"] > config["soiling"]["max_loss"] * 100:
        warnings.append(f"手动污损值超过模型上限 {config['soiling']['max_loss'] * 100:.0f}%，已按上限计算。")
    if params["fixed_cycle_days"] < config["soiling"]["min_clean_interval_days"]:
        warnings.append(
            f"固定周期 {params['fixed_cycle_days']} 天短于最小清洗间隔 {config['soiling']['min_clean_interval_days']} 天，固定周期策略可能与项目约束冲突。"
        )
    if metrics["decision"].get("weather_block"):
        warnings.append("当前天气条件不满足安全窗口；任何策略都不应安排现场清洗。")
    if economics.get("net_gain") is not None and economics["net_gain"] < 0:
        warnings.append("当前时点净收益为负，系统不会推荐立即清洗。")
    if soiling.get("natural_clean_expected"):
        warnings.append("预计降雨达到自然清洁阈值，清洗收益已按配置的自然清洁折减。")
    if abs(float(params["tilt_angle_deg"]) - 35.0) > 0.01:
        warnings.append("倾角影响为演示假设映射，没有实测依据，不应作为工程结论。")
    if float(params["pm2_5"]) > 35.0:
        warnings.append("PM2.5 增量使用演示系数 0.00005，没有实测依据，不应作为工程结论。")
    return warnings


def _one_clean_net(config: dict, context: dict, params: dict, day: int, loss_ratio: float, remaining: int) -> float:
    if remaining < 1:
        return 0.0
    cfg = copy.deepcopy(config)
    cfg["economics"]["horizon_days"] = int(remaining)
    cfg["site"]["days_since_clean"] = int(round(params["dry_days"] + day))
    metrics = compute_metrics(cfg, context, include_sensitivity=False, soiling_override_ratio=loss_ratio)
    net = metrics["economics"].get("net_gain")
    return float(net) if net is not None else 0.0


def _simulate_strategy(kind: str, config: dict, context: dict, params: dict, metrics: dict) -> dict:
    soiling_cfg = config["soiling"]
    safety = config["safety"]
    horizon = int(round(params["horizon_days"]))
    dry_days = int(round(params["dry_days"]))
    threshold = float(params["soiling_threshold_pct"]) / 100.0
    fixed_cycle = int(round(params["fixed_cycle_days"]))
    recovery = float(params["recovery_efficiency"])
    max_loss = soiling_cfg["max_loss"]
    rain_threshold = soiling_cfg["rain_clean_threshold_mm"]
    rain_effect = soiling_cfg["rain_clean_effect"]
    min_interval = soiling_cfg["min_clean_interval_days"]
    theory = float(metrics["economics"]["theory_mwh_day"])
    price = float(params["price_per_kwh"])
    total_clean_cost = float(metrics["economics"]["cleaning_cost"])
    downtime_per_clean = (theory / 24.0) * config["economics"]["downtime_hours"] * price * 1000.0

    initial_loss, daily_rate = _initial_loss(config, context, params)
    baseline_loss = initial_loss
    strategy_loss = initial_loss
    baseline_sum = 0.0
    strategy_sum = 0.0
    clean_days: list[int] = []
    unsafe_attempts = 0
    weather_skips = 0
    interval_skips = 0

    rain_schedule = [float(params["expected_rain_mm"])] + [0.0] * max(0, horizon - 1)
    if dry_days == 0:
        fixed_offset = fixed_cycle
    elif dry_days % fixed_cycle == 0:
        fixed_offset = 0
    else:
        fixed_offset = fixed_cycle - (dry_days % fixed_cycle)

    for day in range(horizon):
        baseline_loss = min(max_loss, baseline_loss + daily_rate)
        strategy_loss = min(max_loss, strategy_loss + daily_rate)
        baseline_sum += baseline_loss

        allowed = dry_days + day >= min_interval
        rain = rain_schedule[day]
        safe = (rain < safety["rain_limit_mm"]) and (float(params["wind_speed_ms"]) < safety["wind_limit_ms"])

        should_clean = False
        if kind == "fixed":
            should_clean = day >= fixed_offset and (day - fixed_offset) % fixed_cycle == 0
            if should_clean and not allowed:
                interval_skips += 1
                should_clean = False
        elif kind == "threshold":
            should_clean = strategy_loss >= threshold and allowed
        elif kind == "joint":
            if strategy_loss >= threshold and allowed:
                if not safe:
                    weather_skips += 1
                else:
                    remaining = horizon - day
                    should_clean = _one_clean_net(config, context, params, day, strategy_loss, remaining) > 0
        else:
            raise ValueError(f"未知策略：{kind}")

        if should_clean:
            if safe:
                strategy_loss = strategy_loss * (1.0 - recovery)
                clean_days.append(day + 1)
            else:
                unsafe_attempts += 1

        strategy_sum += strategy_loss

        if rain >= rain_threshold:
            baseline_loss = baseline_loss * (1.0 - rain_effect)
            strategy_loss = strategy_loss * (1.0 - rain_effect)

    revenue = max(0.0, (baseline_sum - strategy_sum) * theory * price * 1000.0)
    cost = len(clean_days) * (total_clean_cost + downtime_per_clean)
    net = revenue - cost
    payback = (cost / (revenue / horizon)) if revenue > 0 and horizon > 0 else None

    if unsafe_attempts:
        safety_risk = f"高：有 {unsafe_attempts} 次计划落在不安全天气"
    elif interval_skips:
        safety_risk = f"中：有 {interval_skips} 次计划早于最小清洗间隔"
    elif weather_skips:
        safety_risk = f"中：因天气跳过 {weather_skips} 次潜在清洗"
    else:
        safety_risk = "低：未安排不安全天气清洗"

    names = {
        "fixed": "固定周期清洗",
        "threshold": "污损阈值清洗",
        "joint": "天气与经济收益联合决策",
    }
    reasons = {
        "fixed": f"每 {fixed_cycle} 天清洗一次；不考虑天气与单次经济性。",
        "threshold": f"污损损失达到 {params['soiling_threshold_pct']}% 即清洗；不考虑天气与单次经济性。",
        "joint": f"污损损失达到 {params['soiling_threshold_pct']}%，且天气安全、单次清洗净收益为正时才清洗。",
    }
    return {
        "id": kind,
        "name": names[kind],
        "horizon_days": horizon,
        "initial_loss_pct": round(initial_loss * 100, 1),
        "daily_rate_pct": round(daily_rate * 100, 3),
        "clean_count": len(clean_days),
        "clean_days": clean_days,
        "revenue": round(revenue, 0),
        "cost": round(cost, 0),
        "net_gain": round(net, 0),
        "payback_days": round(payback, 1) if payback is not None else None,
        "safety_risk": safety_risk,
        "unsafe_attempts": unsafe_attempts,
        "weather_skips": weather_skips,
        "interval_skips": interval_skips,
        "end_loss_pct": round(strategy_loss * 100, 1),
        "reason": reasons[kind],
    }


def _strategies(config: dict, context: dict, params: dict, metrics: dict) -> list[dict]:
    return [
        _simulate_strategy("fixed", config, context, params, metrics),
        _simulate_strategy("threshold", config, context, params, metrics),
        _simulate_strategy("joint", config, context, params, metrics),
    ]


def _impact(params: dict) -> list[dict]:
    sweeps = [
        ("pm10", "PM10", "μg/m³", [0, 60, 80, 85, 90, 100]),
        ("pm2_5", "PM2.5", "μg/m³", [0, 35, 60, 100, 150]),
        ("price_per_kwh", "上网电价", "元/kWh", [0.1, 0.2, 0.25, 0.4, 0.6]),
        ("cleaning_total", "清洗总成本", "元/次", [2000, 4000, 8000, 12000, 20000]),
        ("recovery_efficiency", "恢复效率", "比例", [0.7, 0.8, 0.9, 0.95, 1.0]),
        ("dry_days", "连续无雨天数", "天", [0, 2, 4, 6, 7, 10]),
        ("expected_rain_mm", "预计降雨", "mm", [0, 1, 2, 3, 8, 15]),
        ("capacity_mw", "装机容量", "MW", [5, 10, 20, 50, 100]),
        ("tilt_angle_deg", "组件倾角", "°", [0, 15, 35, 50, 60]),
    ]
    out = []
    for key, label, unit, values in sweeps:
        points = []
        for value in values:
            p = copy.deepcopy(params)
            if key == "cleaning_total":
                p["labor_cost"] = round(value * 0.5, 0)
                p["water_cost"] = round(value * 0.25, 0)
                p["equipment_cost"] = round(value * 0.25, 0)
            else:
                p[key] = value
            config = _build_config(p)
            context = _build_context(p)
            override = None if p["soiling_override_pct"] is None else p["soiling_override_pct"] / 100.0
            metrics = compute_metrics(config, context, include_sensitivity=False, soiling_override_ratio=override)
            points.append(
                {
                    "value": value,
                    "net_gain": metrics["economics"].get("net_gain"),
                    "action": metrics["decision"]["action"],
                    "loss_pct": metrics["soiling"].get("loss_pct"),
                }
            )
        out.append({"key": key, "label": label, "unit": unit, "points": points})
    return out


def defaults_payload() -> dict:
    return {
        "result_kind": "simulation",
        "disclaimer": DISCLAIMER,
        "scenario_note": SCENARIO_NOTE,
        "params": copy.deepcopy(DEFAULTS),
        "specs": copy.deepcopy(PARAM_SPECS),
        "scenarios": copy.deepcopy(DEMO_SCENARIOS),
        "thresholds": _thresholds(),
        "assumptions": [
            "所有气象、空气质量和污损输入均为用户假设或示例数据，不是真实电站运行数据。",
            "污损率使用 pv_model 的模型估算；手动覆盖值仅用于对照。",
            "倾角影响使用演示假设映射，无实测依据。",
            "三种策略使用相同输入和相同评价周期。",
        ],
        "limitations": [
            "没有真实历史数据，因此结果只能称为模型模拟比较，不能称为真实回测。",
            "污损累积为线性模型，未建模沙尘事件突发性和组件类型差异。",
            "策略模拟按日粒度，未建模清洗作业的具体时段、班组安排和局部遮挡。",
            "电价、清洗成本和降雨均为输入假设，不代表实际合同或气象预报。",
        ],
    }


def calculate(payload: dict | None = None) -> dict:
    params = _normalize(payload)
    scenario_name = (payload or {}).get("scenario_name") or "自定义模拟场景"
    config = _build_config(params)
    context = _build_context(params)
    override = None if params["soiling_override_pct"] is None else params["soiling_override_pct"] / 100.0
    metrics = compute_metrics(config, context, include_sensitivity=False, soiling_override_ratio=override)
    warnings = _warnings(metrics, params, config)
    summary = _summary(metrics, params, warnings)
    strategies = _strategies(config, context, params, metrics)
    impact = _impact(params)
    return {
        "result_kind": "simulation",
        "disclaimer": DISCLAIMER,
        "scenario_name": str(scenario_name)[:80],
        "scenario_note": SCENARIO_NOTE,
        "generated_at": now_iso(),
        "params": params,
        "thresholds": _thresholds(),
        "summary": summary,
        "metrics": metrics,
        "strategies": strategies,
        "impact": impact,
        "warnings": warnings,
        "assumptions": defaults_payload()["assumptions"],
        "limitations": defaults_payload()["limitations"],
        "formulas": {
            "soiling": "污损损失率 = min(上限, 日污损速率 × 天数 × 倾角演示因子)；日污损速率 = 基础速率 + max(0, PM10 − 基准) × 系数 + max(0, PM2.5 − 35) × 演示系数",
            "theory": "理论日发电量 = 装机容量 × 日辐照 × 系统效率（模拟实验室使用降级公式）",
            "revenue": "预计发电收益 = 理论日发电量 × 污损损失率 × 恢复效率 × (1 − 自然清洁折减) × 1000 × 电价 × 评价周期",
            "net": "净收益 = 预计发电收益 − 清洗总成本 − 停机损失",
            "strategies": "三种策略按同一输入、同一评价周期逐日模拟；固定周期与阈值策略不考虑经济性，联合策略仅在天气安全且单次净收益为正时清洗。",
        },
    }