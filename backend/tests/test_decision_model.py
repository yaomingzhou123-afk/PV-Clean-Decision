import json
from pathlib import Path

import pytest

from pv_model import assess_environment, compute_metrics

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "data" / "pv_config.json").read_text(encoding="utf-8"))


def make_context(irradiance=5.8, rain=0.0, wind=9.0, theoretical=None, pm10=135.0, dust=120.0, quality="demo"):
    days = [
        {"date": f"D{i+1}", "irradiance": irradiance, "rain": rain, "wind": wind, "cloud": 10, "temp_max": 5.0, "temp_min": -2.0}
        for i in range(3)
    ]
    return {
        "forecast": {"days": days, "source": "demo", "quality": "demo", "fetched_at": "t"},
        "air": {"pm10": pm10, "pm2_5": 24.0, "dust": dust, "source": "demo", "quality": "demo"},
        "theoretical": theoretical,
        "quality": quality,
        "fetched_at": "t",
        "data_source_records": [],
    }


def cfg_copy():
    return json.loads(json.dumps(CONFIG))


def test_decision_clean():
    m = compute_metrics(CONFIG, make_context())
    assert m["decision"]["action"] == "clean"


def test_decision_defer_on_rain():
    m = compute_metrics(CONFIG, make_context(rain=3.0))
    assert m["decision"]["action"] == "defer"
    assert m["decision"]["weather_block"] is True


def test_decision_hold_on_interval():
    cfg = cfg_copy()
    cfg["site"]["days_since_clean"] = 2
    m = compute_metrics(cfg, make_context())
    assert m["decision"]["action"] == "hold"
    assert m["decision"]["interval_block"] is True


def test_decision_hold_on_negative_economics():
    cfg = cfg_copy()
    cfg["economics"]["cleaning_cost"] = 10_000_000
    m = compute_metrics(cfg, make_context())
    assert m["decision"]["action"] == "hold"
    assert m["economics"]["net_gain"] < 0


def test_decision_insufficient_data_on_empty_forecast():
    ctx = make_context()
    ctx["forecast"]["days"] = []
    m = compute_metrics(CONFIG, ctx)
    assert m["decision"]["action"] == "insufficient_data"
    assert m["decision"]["data_insufficient"]


def test_decision_insufficient_data_on_live_fallback():
    cfg = cfg_copy()
    cfg["scenario"] = "live"
    m = compute_metrics(cfg, make_context(quality="fallback"))
    assert m["decision"]["action"] == "insufficient_data"
    assert any("实时数据获取失败" in p for p in m["decision"]["data_insufficient"])


def test_zero_cost_still_clean():
    cfg = cfg_copy()
    cfg["economics"]["cleaning_cost"] = 0
    m = compute_metrics(cfg, make_context())
    assert m["economics"]["net_gain"] > 0
    assert m["decision"]["action"] == "clean"


def test_missing_price_raises():
    cfg = cfg_copy()
    cfg["economics"]["price_per_kwh"] = 0
    with pytest.raises(ValueError, match="price_per_kwh"):
        compute_metrics(cfg, make_context())


def test_itemized_cost_breakdown():
    cfg = cfg_copy()
    cfg["economics"]["labor_cost"] = 2000
    cfg["economics"]["water_cost"] = 1000
    cfg["economics"]["equipment_cost"] = 1000
    m = compute_metrics(cfg, make_context())
    assert m["economics"]["cost_breakdown"]["mode"] == "itemized"
    assert m["economics"]["cost_breakdown"]["total"] == 4000
    assert m["economics"]["cleaning_cost"] == 4000


def test_recovery_efficiency_reduces_revenue():
    m95 = compute_metrics(CONFIG, make_context())
    cfg = cfg_copy()
    cfg["economics"]["recovery_efficiency"] = 1.0
    m100 = compute_metrics(cfg, make_context())
    assert m95["economics"]["net_gain"] < m100["economics"]["net_gain"]


def test_natural_clean_discount_applies():
    m = compute_metrics(CONFIG, make_context(rain=3.0))
    assert m["soiling"]["natural_clean_expected"] is True
    assert m["economics"]["natural_clean_discount"] == 0.7


def test_no_rain_no_discount():
    m = compute_metrics(CONFIG, make_context(rain=0.0))
    assert m["economics"]["natural_clean_discount"] == 1.0


def test_sensitivity_method_and_scenario_count():
    m = compute_metrics(CONFIG, make_context())
    s = m["sensitivity"]
    assert s["method"] == "one_factor_deterministic"
    assert len(s["scenarios"]) == 12
    assert all("net_gain" in sc or "error" in sc for sc in s["scenarios"])


def test_sensitivity_detects_decision_flip():
    cfg = cfg_copy()
    cfg["economics"]["cleaning_cost"] = 38000
    m = compute_metrics(cfg, make_context())
    flips = [sc for sc in m["sensitivity"]["scenarios"] if sc.get("flips_decision")]
    assert flips, "应至少有一个扰动场景触发决策翻转"


def test_sensitivity_declares_not_monte_carlo():
    m = compute_metrics(CONFIG, make_context())
    note = m["sensitivity"]["note"]
    assert "非蒙特卡洛" in note or "无概率分布假设" in note


def test_soiling_is_model_estimate_not_measured():
    m = compute_metrics(CONFIG, make_context())
    assert m["soiling"]["method"] == "model_estimate"
    assert any("非实测" in lim for lim in m["soiling"]["limitations"])


def test_soiling_evidence_has_drivers_and_basis():
    m = compute_metrics(CONFIG, make_context())
    assert m["soiling"]["drivers"]
    assert "base_rate_per_day" in m["soiling"]["param_basis"]
    assert m["soiling"]["data_completeness"]["pm10"] is True


def test_environment_layer_reports_completeness():
    env = assess_environment(CONFIG, make_context())
    assert env["data_completeness"]["forecast_days"] == 3
    assert env["data_completeness"]["pm2_5"] is True
    assert env["natural_clean_expected"] is False


def test_wind_over_limit_defers():
    m = compute_metrics(CONFIG, make_context(wind=15.0))
    assert m["decision"]["action"] == "defer"


def test_rain_threshold_configurable():
    cfg = cfg_copy()
    cfg["safety"]["rain_limit_mm"] = 10.0
    m = compute_metrics(cfg, make_context(rain=3.0))
    assert m["decision"]["weather_block"] is False