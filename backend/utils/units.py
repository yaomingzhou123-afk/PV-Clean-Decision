def _to_float(value) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def mj_to_kwh(value) -> float | None:
    """MJ/m² → kWh/m²（÷3.6）。输入 None/非数字/负数返回 None。"""
    v = _to_float(value)
    if v is None or v < 0:
        return None
    return round(v / 3.6, 2)


def kmh_to_ms(value) -> float | None:
    """km/h → m/s（÷3.6）。输入 None/非数字/负数返回 None。"""
    v = _to_float(value)
    if v is None or v < 0:
        return None
    return round(v / 3.6, 1)


def valid_irradiance_kwh(value, lo: float = 0.0, hi: float = 12.0) -> float | None:
    """日辐照合理范围校验（单位 kWh/m²，典型 0–12）。不合法返回 None，拒绝进入正式计算。"""
    v = _to_float(value)
    if v is None or v < lo or v > hi:
        return None
    return round(v, 2)


def valid_wind_ms(value, lo: float = 0.0, hi: float = 60.0) -> float | None:
    """风速合理范围校验（单位 m/s，0–60 覆盖极端阵风）。不合法返回 None。"""
    v = _to_float(value)
    if v is None or v < lo or v > hi:
        return None
    return round(v, 1)


def valid_rain_mm(value, lo: float = 0.0, hi: float = 500.0) -> float | None:
    """日降水合理范围校验（单位 mm，0–500 覆盖极端暴雨）。不合法返回 None。"""
    v = _to_float(value)
    if v is None or v < lo or v > hi:
        return None
    return round(v, 1)