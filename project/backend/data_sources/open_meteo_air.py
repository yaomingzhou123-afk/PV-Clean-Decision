from data_sources.base import fetch_json, valid_coords
from data_sources.models import error_record, make_record

AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
SOURCE = "open-meteo-air"
DATA_TYPE = "air_quality_forecast"
DATA_KIND = "forecast"

UNITS = {"pm10": "μg/m³", "pm2_5": "μg/m³", "dust": "μg/m³"}


def _avg(values: list) -> float | None:
    valid = [v for v in values if isinstance(v, (int, float)) and 0 <= v <= 2000]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 1)


async def get_air(lat: float, lng: float) -> dict:
    """获取 48 小时空气质量预报（forecast，非地面监测站实测数据）。
    返回 {"record": DataRecord, "air": {"pm10","pm2_5","dust"}|None}。"""
    if not valid_coords(lat, lng):
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, "经纬度非法"), "air": None}
    params = {
        "latitude": lat,
        "longitude": lng,
        "hourly": "pm10,pm2_5,dust",
        "forecast_days": 2,
        "timezone": "Asia/Shanghai",
    }
    data, err = await fetch_json(AIR_URL, params, source=SOURCE, data_kind=DATA_KIND)
    if err:
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, err), "air": None}
    hourly = (data or {}).get("hourly") or {}
    pm10 = _avg(hourly.get("pm10") or [])
    if pm10 is None:
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, "接口返回但 PM10 无有效值"), "air": None}
    air = {
        "pm10": pm10,
        "pm2_5": _avg(hourly.get("pm2_5") or []),
        "dust": _avg(hourly.get("dust") or []),
    }
    times = hourly.get("time") or []
    record = make_record(
        source=SOURCE,
        data_type=DATA_TYPE,
        data_kind=DATA_KIND,
        latitude=lat,
        longitude=lng,
        value=air,
        unit=UNITS,
        valid_time=f"{times[0] if times else '?'} ~ {times[-1] if times else '?'}",
    )
    return {"record": record, "air": air}