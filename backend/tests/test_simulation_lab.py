import pytest

from simulation_lab import DEMO_SCENARIOS, DEFAULTS, calculate, defaults_payload


def signature(result):
    summary = result["summary"]
    return (
        summary["net_gain"],
        summary["decision"]["action"],
        tuple((s["id"], s["clean_count"], s["net_gain"]) for s in result["strategies"]),
    )


def test_defaults_payload_is_simulation_and_has_required_params():
    payload = defaults_payload()
    assert payload["result_kind"] == "simulation"
    assert "不代表真实电站" in payload["disclaimer"]
    assert len(payload["scenarios"]) == 3
    keys = {spec["key"] for spec in payload["specs"]}
    assert {
        "pm10", "pm2_5", "dry_days", "soiling_override_pct", "capacity_mw",
        "tilt_angle_deg", "price_per_kwh", "labor_cost", "water_cost",
        "equipment_cost", "expected_rain_mm", "wind_speed_ms",
        "recovery_efficiency",
    } <= keys
    for spec in payload["specs"]:
        assert spec["unit"]
        assert spec["min"] <= spec["default"] if spec["default"] is not None else True
        assert spec["max"] >= spec["min"]
        assert spec["description"] and spec["basis"]


def test_result_is_explicitly_marked_as_simulation():
    result = calculate({})
    assert result["result_kind"] == "simulation"
    assert "不代表真实电站" in result["disclaimer"]
    assert "真实回测" in result["disclaimer"]
    record = result["metrics"]["data_quality"]["data_sources"][0]
    assert record["data_kind"] == "simulation"
    assert record["is_simulated"] is True
    assert result["summary"]["soiling_risk"]["method"] == "model_estimate"


def test_default_summary_and_strategy_shapes():
    result = calculate({})
    summary = result["summary"]
    assert summary["decision"]["action"] == "clean"
    assert summary["net_gain"] > 0
    assert summary["cost"]["cleaning_total"] == 4000
    assert len(result["strategies"]) == 3
    assert {s["id"] for s in result["strategies"]} == {"fixed", "threshold", "joint"}
    for strategy in result["strategies"]:
        assert strategy["horizon_days"] == DEFAULTS["horizon_days"]
        assert strategy["clean_count"] >= 0
        assert strategy["revenue"] >= 0
        assert strategy["cost"] >= 0
        assert strategy["reason"]


@pytest.mark.parametrize(
    "key,value",
    [
        ("pm10", 100),
        ("pm2_5", 80),
        ("dry_days", 30),
        ("capacity_mw", 40),
        ("tilt_angle_deg", 60),
        ("price_per_kwh", 0.4),
        ("labor_cost", 3000),
        ("water_cost", 2000),
        ("equipment_cost", 2000),
        ("expected_rain_mm", 8),
        ("wind_speed_ms", 15),
        ("recovery_efficiency", 0.8),
        ("avg_irradiance_kwh_m2_day", 7),
        ("horizon_days", 15),
        ("fixed_cycle_days", 7),
        ("soiling_threshold_pct", 8),
        ("soiling_override_pct", 10),
    ],
)
def test_each_core_parameter_recalculates_result(key, value):
    base = calculate({})
    changed = calculate({key: value})
    assert signature(base) != signature(changed), f"{key} 变化后结果未重算"


def test_negative_net_gain_never_recommends_clean():
    result = calculate({
        "pm10": 80,
        "dry_days": 20,
        "labor_cost": 20000,
        "water_cost": 10000,
        "equipment_cost": 30000,
    })
    assert result["summary"]["net_gain"] < 0
    assert result["summary"]["decision"]["action"] != "clean"


def test_unsafe_weather_never_recommends_clean():
    wind = calculate({"wind_speed_ms": 15})
    rain = calculate({"expected_rain_mm": 8})
    for result in (wind, rain):
        assert result["summary"]["weather"]["blocked"] is True
        assert result["summary"]["decision"]["action"] != "clean"
        assert any("天气条件" in warning for warning in result["warnings"])


def test_strategies_use_same_horizon_and_expose_safety_risk():
    result = calculate({"wind_speed_ms": 15})
    horizons = {s["horizon_days"] for s in result["strategies"]}
    assert horizons == {DEFAULTS["horizon_days"]}
    assert all(s["safety_risk"] for s in result["strategies"])
    assert any(s["unsafe_attempts"] > 0 or s["weather_skips"] > 0 for s in result["strategies"])


def test_three_example_scenarios_marked_as_assumptions():
    by_id = {scenario["id"]: scenario for scenario in DEMO_SCENARIOS}
    assert set(by_id) == {"A", "B", "C"}
    a = calculate({**by_id["A"]["params"], "scenario_name": by_id["A"]["name"]})
    b = calculate({**by_id["B"]["params"], "scenario_name": by_id["B"]["name"]})
    c = calculate({**by_id["C"]["params"], "scenario_name": by_id["C"]["name"]})
    assert a["summary"]["decision"]["action"] == "clean"
    assert b["summary"]["decision"]["action"] == "defer"
    assert c["summary"]["decision"]["action"] == "hold"
    for result, scenario in ((a, by_id["A"]), (b, by_id["B"]), (c, by_id["C"])):
        assert result["scenario_name"] == scenario["name"]
        assert "示例" in result["scenario_note"]


def test_manual_override_is_clamped_and_warned():
    result = calculate({"soiling_override_pct": 25})
    assert result["summary"]["soiling_risk"]["loss_pct"] == 15.0
    assert result["summary"]["soiling_risk"]["override_applied"] is True
    assert result["summary"]["soiling_risk"]["method"] == "user_assumption"
    assert any("超过模型上限" in warning for warning in result["warnings"])


def test_pm25_changes_soiling_when_pm10_is_not_at_cap():
    low = calculate({"pm10": 80, "pm2_5": 24})
    high = calculate({"pm10": 80, "pm2_5": 80})
    assert high["summary"]["soiling_risk"]["loss_pct"] > low["summary"]["soiling_risk"]["loss_pct"]
    assert high["summary"]["net_gain"] > low["summary"]["net_gain"]


def test_fixed_cycle_shorter_than_min_interval_warns():
    result = calculate({"fixed_cycle_days": 7})
    assert any("短于最小清洗间隔" in warning for warning in result["warnings"])


def test_impact_curves_are_generated_from_recalculation():
    result = calculate({})
    assert result["impact"]
    for item in result["impact"]:
        assert item["label"] and item["unit"]
        assert len(item["points"]) >= 4
        for point in item["points"]:
            assert set(point) >= {"value", "net_gain", "action", "loss_pct"}


def test_invalid_values_raise_clear_errors():
    with pytest.raises(ValueError, match="PM10"):
        calculate({"pm10": 9999})
    with pytest.raises(ValueError, match="装机容量"):
        calculate({"capacity_mw": 0})
    with pytest.raises(ValueError, match="风速"):
        calculate({"wind_speed_ms": -1})
    with pytest.raises(ValueError, match="必须"):
        calculate({"recovery_efficiency": 2})


def test_api_defaults_and_invalid_input():
    from fastapi.testclient import TestClient

    import main

    client = TestClient(main.app)
    assert client.get("/api/simulation/defaults").status_code == 200
    ok = client.post("/api/simulation/calculate", json={"pm10": 80, "dry_days": 20})
    assert ok.status_code == 200
    assert ok.json()["result_kind"] == "simulation"
    bad = client.post("/api/simulation/calculate", json={"pm10": 9999})
    assert bad.status_code == 422
    assert bad.json()["detail"]