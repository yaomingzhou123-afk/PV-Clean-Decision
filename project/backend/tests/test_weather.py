from weather import _daily_to_raw_days, demo_context, sanitize_days


def test_sanitize_days_keeps_only_fully_valid_rows():
    raw = [
        {"date": "D1", "irradiance": 5.9, "rain": 0.0, "wind": 8.0, "cloud": 5},
        {"date": "D2", "irradiance": 6.1, "rain": None, "wind": -3, "cloud": 120},
    ]
    days = sanitize_days(raw)
    assert days is not None
    assert len(days) == 1
    assert days[0]["date"] == "D1"
    assert days[0]["irradiance"] == 5.9
    assert days[0]["wind"] == 8.0


def test_sanitize_days_drops_missing_wind_or_rain():
    raw = [
        {"date": "D1", "irradiance": 5.9, "rain": 0.0, "wind": None, "cloud": 5},
        {"date": "D2", "irradiance": 6.1, "rain": None, "wind": 9.0, "cloud": 5},
    ]
    assert sanitize_days(raw) is None


def test_sanitize_days_cloud_missing_defaults_zero():
    raw = [{"date": "D1", "irradiance": 5.9, "rain": 0.0, "wind": 8.0, "cloud": None}]
    days = sanitize_days(raw)
    assert days is not None
    assert days[0]["cloud"] == 0.0


def test_daily_to_raw_days_converts_mj_to_kwh_once():
    daily = {
        "time": ["2026-11-15", "2026-11-16"],
        "shortwave_radiation_sum": [18.0, 3.6],
        "precipitation_sum": [0.0, 1.2],
        "wind_speed_10m_max": [10.0, 12.5],
        "cloud_cover_mean": [10, 30],
    }
    raw = _daily_to_raw_days(daily)
    assert raw[0]["irradiance"] == 5.0
    assert raw[1]["irradiance"] == 1.0
    assert raw[0]["wind"] == 10.0
    days = sanitize_days(raw)
    assert days is not None
    assert days[0]["irradiance"] == 5.0
    assert days[1]["irradiance"] == 1.0


def test_daily_to_raw_days_missing_fields_yield_none():
    daily = {"time": ["2026-11-15"]}
    raw = _daily_to_raw_days(daily)
    assert raw[0]["irradiance"] is None
    assert raw[0]["wind"] is None
    assert raw[0]["rain"] is None


def test_sanitize_days_rejects_invalid_irradiance():
    raw = [
        {"date": "D1", "irradiance": -1, "rain": 0, "wind": 5, "cloud": 0},
        {"date": "D2", "irradiance": 99, "rain": 0, "wind": 5, "cloud": 0},
        {"date": "D3", "irradiance": None, "rain": 0, "wind": 5, "cloud": 0},
    ]
    assert sanitize_days(raw) is None


def test_sanitize_days_empty_returns_none():
    assert sanitize_days([]) is None
    assert sanitize_days(None) is None


def test_demo_context_marked_as_demo():
    ctx = demo_context()
    assert ctx["quality"] == "demo"
    assert ctx["forecast"]["quality"] == "demo"
    assert ctx["forecast"]["source"] == "demo"
    assert ctx["theoretical"] is None
    assert ctx["fetched_at"]