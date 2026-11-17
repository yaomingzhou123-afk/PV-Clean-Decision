import json
from pathlib import Path

from agents import (
    apply_partial,
    arbitrate,
    critic_defer_review,
    economics_opinion,
    ops_opinion,
    partial_ratio,
    soiling_opinion,
    weather_opinion,
)

CONFIG = json.loads((Path(__file__).resolve().parents[1] / "data" / "pv_config.json").read_text(encoding="utf-8"))


def make_metrics(loss_pct=15.0, rain=0.0, wind=9.0, net_gain=40000.0, horizon_revenue=50000.0):
    loss_ratio = round(loss_pct / 100, 4)
    return {
        "weather": {
            "days": [{"date": f"D{i+1}", "irradiance": 5.8, "rain": rain, "wind": wind, "cloud": 10} for i in range(3)],
            "rain_next48": rain,
            "wind_max": wind,
            "avg_irradiance": 5.8,
            "best_date": "D2",
            "best_irradiance": 6.1,
            "source": "demo",
        },
        "soiling": {"loss_pct": loss_pct, "loss_ratio": loss_ratio, "pm10": 135.0, "dust": 120.0, "days": 20},
        "economics": {
            "net_gain": net_gain,
            "horizon_revenue": horizon_revenue,
            "cleaning_cost": 4000,
            "downtime_loss": 3963,
            "horizon_days": 14,
            "payback_days": 1.1,
            "daily_revenue": 3567.0,
            "recoverable_mwh_day": 14.27,
            "price_per_kwh": 0.25,
        },
        "decision": {
            "action": "clean" if net_gain > 0 and rain == 0.0 and wind < 12 else ("defer" if rain >= 1.0 or wind >= 12 else "hold"),
            "window": "D2",
            "weather_block": rain >= 1.0 or wind >= 12,
            "economics_ok": net_gain > 0,
            "reason": "test",
        },
    }


def test_opinions_expose_confidence_and_evidence():
    m = make_metrics()
    for evt in (weather_opinion(m, CONFIG), soiling_opinion(m, CONFIG), economics_opinion(m, CONFIG), ops_opinion(m, CONFIG)):
        assert 0.6 <= evt["confidence"] <= 0.99
        assert isinstance(evt["evidence"], list) and evt["evidence"]
        for e in evt["evidence"]:
            assert {"metric", "value", "threshold", "unit", "verdict", "margin_ratio"} <= set(e)


def test_confidence_is_deterministic():
    m = make_metrics()
    a = weather_opinion(m, CONFIG)
    b = weather_opinion(m, CONFIG)
    assert a["confidence"] == b["confidence"]


def test_confidence_grows_with_margin():
    borderline = weather_opinion(make_metrics(rain=0.99), CONFIG)
    clear = weather_opinion(make_metrics(rain=0.0), CONFIG)
    assert clear["confidence"] > borderline["confidence"]


def test_low_soiling_threshold_from_config():
    m = make_metrics(loss_pct=8.0)
    assert soiling_opinion(m, CONFIG)["stance"] == "support"
    cfg = json.loads(json.dumps(CONFIG))
    cfg["soiling"]["low_soiling_threshold_pct"] = 10
    assert soiling_opinion(m, cfg)["stance"] == "object"


def test_partial_ratio_follows_soiling_distribution():
    high = partial_ratio(make_metrics(loss_pct=15.0), CONFIG)
    low = partial_ratio(make_metrics(loss_pct=5.0), CONFIG)
    assert high > low
    assert CONFIG["negotiation"]["partial_min_ratio"] <= low <= high <= CONFIG["negotiation"]["partial_max_ratio"]


def test_arbitrate_uses_configured_ratio():
    m = make_metrics(net_gain=-1000.0)
    evt = arbitrate(m, CONFIG)
    ratio = evt["patch"]["cost_ratio"]
    assert evt["patch"]["partial"] is True
    assert CONFIG["negotiation"]["partial_min_ratio"] <= ratio <= CONFIG["negotiation"]["partial_max_ratio"]


def test_apply_partial_scales_with_ratio():
    m = make_metrics(net_gain=-1000.0)
    updated = apply_partial(m, CONFIG)
    assert updated["economics"]["scope"] == "partial"
    assert updated["economics"]["scope_ratio"] == int(partial_ratio(m, CONFIG) * 100)


def test_defer_review_supports_consistent_block():
    m = make_metrics(rain=5.0)
    m["decision"]["action"] = "defer"
    m["decision"]["weather_block"] = True
    passed, evt = critic_defer_review(m, CONFIG)
    assert passed is True
    assert evt["stance"] == "support"
    assert evt["evidence"]


def test_defer_review_rejects_inconsistent_block():
    m = make_metrics(rain=0.0)
    m["decision"]["action"] = "defer"
    m["decision"]["weather_block"] = True
    passed, evt = critic_defer_review(m, CONFIG)
    assert passed is False
    assert evt["stance"] == "object"