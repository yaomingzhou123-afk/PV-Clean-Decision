from utils.units import kmh_to_ms, mj_to_kwh, valid_irradiance_kwh, valid_rain_mm, valid_wind_ms


def test_mj_to_kwh_18_to_5():
    assert mj_to_kwh(18) == 5.0


def test_mj_to_kwh_basic_values():
    assert mj_to_kwh(3.6) == 1.0
    assert mj_to_kwh(0) == 0.0
    assert mj_to_kwh(21.6) == 6.0


def test_kmh_to_ms_36_to_10():
    assert kmh_to_ms(36) == 10.0


def test_kmh_to_ms_basic_values():
    assert kmh_to_ms(43.2) == 12.0
    assert kmh_to_ms(0) == 0.0


def test_mj_to_kwh_rejects_invalid():
    assert mj_to_kwh(None) is None
    assert mj_to_kwh("abc") is None
    assert mj_to_kwh(-1) is None
    assert mj_to_kwh([1]) is None
    assert mj_to_kwh(True) is None


def test_kmh_to_ms_rejects_invalid():
    assert kmh_to_ms(None) is None
    assert kmh_to_ms("fast") is None
    assert kmh_to_ms(-5) is None


def test_missing_value_rejected_from_calculation():
    assert valid_irradiance_kwh(None) is None
    assert valid_wind_ms(None) is None
    assert valid_rain_mm(None) is None


def test_irradiance_range_guard():
    assert valid_irradiance_kwh(5.0) == 5.0
    assert valid_irradiance_kwh(12.0) == 12.0
    assert valid_irradiance_kwh(12.01) is None
    assert valid_irradiance_kwh(-0.1) is None


def test_wind_range_guard():
    assert valid_wind_ms(10.0) == 10.0
    assert valid_wind_ms(60.0) == 60.0
    assert valid_wind_ms(60.1) is None
    assert valid_wind_ms(-1) is None


def test_no_double_conversion_in_pipeline():
    from weather import _daily_to_raw_days, sanitize_days

    daily = {
        "time": ["2026-11-15"],
        "shortwave_radiation_sum": [18.0],
        "precipitation_sum": [0.0],
        "wind_speed_10m_max": [10.0],
        "cloud_cover_mean": [10],
    }
    raw = _daily_to_raw_days(daily)
    assert raw[0]["irradiance"] == 5.0
    days = sanitize_days(raw)
    assert days is not None
    assert days[0]["irradiance"] == 5.0
    assert days[0]["wind"] == 10.0


def test_mj_input_converted_once_not_twice():
    assert mj_to_kwh(mj_to_kwh(18)) != mj_to_kwh(18)
    assert mj_to_kwh(18) == 5.0