from weather import demo_context, sanitize_days


def test_sanitize_days_keeps_valid_rows():
    raw = [
        {"date": "D1", "irradiance": 5.9, "rain": 0.0, "wind": 8.0, "cloud": 5},
        {"date": "D2", "irradiance": 6.1, "rain": None, "wind": -3, "cloud": 120},
    ]
    days = sanitize_days(raw)
    assert len(days) == 2
    assert days[0]["irradiance"] == 5.9
    assert days[1]["rain"] == 0.0
    assert days[1]["wind"] == 0.0
    assert days[1]["cloud"] == 0.0


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