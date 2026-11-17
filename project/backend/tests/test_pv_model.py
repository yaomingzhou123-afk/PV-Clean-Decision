import json
from pathlib import Path

import pytest

from pv_model import compute_metrics, estimate_soiling, validate_config

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "data" / "pv_config.json").read_text(encoding="utf-8"))


def make_context(irradiance=5.8, rain=0.0, wind=9.0, theoretical=None):
    days = [
        {"date": f"D{i+1}", "irradiance": irradiance, "rain": rain, "wind": wind, "cloud": 10}
        for i in range(3)
    ]
    return {
        "forecast": {"days": days, "source": "demo", "quality": "demo", "fetched_at": "t"},
        "air": {"pm10": 135.0, "dust": 120.0, "source": "demo", "quality": "demo"},
        "theoretical": theoretical,
        "quality": "demo",
    }


def test_soiling_clamped_by_max_loss():
    cfg = json.loads(json.dumps(CONFIG))
    cfg["site"]["days_since_clean"] = 400
    s = estimate_soiling(cfg, {"pm10": 135})
    assert s["loss_pct"] <= cfg["soiling"]["max_loss"] * 100


def test_soiling_pm10_below_reference_adds_nothing():
    cfg = json.loads(json.dumps(CONFIG))
    cfg["site"]["days_since_clean"] = 10
    s = estimate_soiling(cfg, {"pm10": 50})
    assert s["loss_pct"] == round(cfg["soiling"]["base_rate_per_day"] * 10 * 100, 1)


def test_invalid_capacity_raises():
    cfg = json.loads(json.dumps(CONFIG))
    cfg["site"]["capacity_mw"] = 0
    with pytest.raises(ValueError, match="capacity_mw"):
        validate_config(cfg)


def test_negative_price_raises():
    cfg = json.loads(json.dumps(CONFIG))
    cfg["economics"]["price_per_kwh"] = -0.1
    with pytest.raises(ValueError, match="price_per_kwh"):
        validate_config(cfg)


def test_empty_days_returns_insufficient_data():
    ctx = make_context()
    ctx["forecast"]["days"] = []
    m = compute_metrics(CONFIG, ctx)
    assert m["decision"]["action"] == "insufficient_data"
    assert m["decision"]["data_insufficient"]
    assert m["economics"]["net_gain"] is None


def test_interval_blocks_clean_when_too_recent():
    cfg = json.loads(json.dumps(CONFIG))
    cfg["site"]["days_since_clean"] = 2
    m = compute_metrics(cfg, make_context())
    assert m["decision"]["action"] == "hold"
    assert m["decision"]["interval_block"] is True
    assert m["decision"]["min_clean_interval_days"] == 14


def test_interval_allows_clean_at_boundary():
    cfg = json.loads(json.dumps(CONFIG))
    cfg["site"]["days_since_clean"] = 14
    m = compute_metrics(cfg, make_context())
    assert m["decision"]["interval_block"] is False


def test_clean_decision_with_formula_source():
    m = compute_metrics(CONFIG, make_context())
    assert m["decision"]["action"] == "clean"
    assert m["economics"]["theoretical_source"] == "formula"
    assert m["economics"]["net_gain"] > 0


def test_clean_decision_with_pvgis_source():
    theoretical = {"E_d": 5.9, "month": 11, "radiation_db": "PVGIS-ERA5", "year_min": 2005, "year_max": 2023, "cached": False, "source": "pvgis"}
    m = compute_metrics(CONFIG, make_context(theoretical=theoretical))
    assert m["economics"]["theoretical_source"] == "pvgis"
    assert m["economics"]["theory_mwh_day"] == round(CONFIG["site"]["capacity_mw"] * 5.9, 1)
    assert m["formulas"]["param_sources"]["base_rate_per_day"]


def test_defer_decision_on_rain():
    m = compute_metrics(CONFIG, make_context(rain=3.0))
    assert m["decision"]["action"] == "defer"
    assert m["decision"]["weather_block"] is True


def test_wind_boundary_11_9_ms_allows_clean():
    m = compute_metrics(CONFIG, make_context(wind=11.9))
    assert m["decision"]["weather_block"] is False
    assert m["decision"]["action"] == "clean"


def test_wind_boundary_12_ms_defers():
    m = compute_metrics(CONFIG, make_context(wind=12.0))
    assert m["decision"]["weather_block"] is True
    assert m["decision"]["action"] == "defer"


def test_hold_decision_when_net_negative():
    cfg = json.loads(json.dumps(CONFIG))
    cfg["economics"]["cleaning_cost"] = 10_000_000
    m = compute_metrics(cfg, make_context())
    assert m["decision"]["action"] == "hold"


def test_metrics_expose_formulas_and_sources():
    m = compute_metrics(CONFIG, make_context())
    assert {"theory", "soiling", "revenue", "net", "downtime"} <= set(m["formulas"])
    assert m["formulas"]["param_sources"].get("price_per_kwh")