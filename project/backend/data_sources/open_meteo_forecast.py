from data_sources.base import fetch_json, valid_coords
from data_sources.models import error_record, make_record
from utils.units import mj_to_kwh, valid_irradiance_kwh, valid_rain_mm, valid_temp_c, valid_wind_ms

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open-meteo-forecast"
DATA_TYPE = "weather_forecast"
DATA_KIND = "forecast"

UNITS = {
    "irradiance": "kWh/m²",
    "rain": "mm",
    "wind": "m/s",
    "cloud": "%",
    "temp_max": "°C",
    "temp_min": "°C",
}


def _daily_to_raw_days(daily: dict) -> list:
    """Open-Meteo daily 响应 → 原始天列表。
    输入单位：shortwave_radiation_sum = MJ/m²；wind_speed_10m_max = m/s（请求已声明 wind_speed_unit=ms）。
    输出单位：irradiance = kWh/m²（本函数完成全项目唯一一次 MJ→kWh 转换）；其余原样传递待校验。"""
    time_list = daily.get("time") or []
    radiation = daily.get("shortwave_radiation_sum") or []
    rain = daily.get("precipitation_sum") or []
    wind = daily.get("wind_speed_10m_max") or []
    cloud = daily.get("cloud_cover_mean") or []
    temp_max = daily.get("temperature_2m_max") or []
    temp_min = daily.get("temperature_2m_min") or []
    raw = []
    for i, day in enumerate(time_list):
        raw.append(
            {
                "date": day,
                "irradiance": mj_to_kwh(radiation[i]) if i < len(radiation) else None,
                "rain": rain[i] if i < len(rain) else None,
                "wind": wind[i] if i < len(wind) else None,
                "cloud": cloud[i] if i < len(cloud) else None,
                "temp_max": temp_max[i] if i < len(temp_max) else None,
                "temp_min": temp_min[i] if i < len(temp_min) else None,
            }
        )
    return raw


def sanitize_days(raw_days: list) -> list | None:
    """校验原始天数据（输入单位：irradiance=kWh/m²、wind=m/s、rain=mm、temp=°C）。
    irradiance/wind/rain 任一缺失或越界即剔除该天，不参与正式计算；
    cloud 与温度仅用于展示，缺失置 None。全部无效返回 None。"""
    days = []
    for d in raw_days or []:
        irr = valid_irradiance_kwh(d.get("irradiance"))
        wind = valid_wind_ms(d.get("wind"))
        rain = valid_rain_mm(d.get("rain"))
        if irr is None or wind is None or rain is None:
            continue
        cloud = d.get("cloud")
        days.append(
            {
                "date": str(d.get("date", "")),
                "irradiance": irr,
                "rain": rain,
                "wind": wind,
                "cloud": round(float(cloud), 0) if isinstance(cloud, (int, float)) and 0 <= cloud <= 100 else 0.0,
                "temp_max": valid_temp_c(d.get("temp_max")),
                "temp_min": valid_temp_c(d.get("temp_min")),
            }
        )
    return days or None


async def get_forecast(lat: float, lng: float) -> dict:
    """获取 3 天天气预报（forecast，非实测）。返回 {"record": DataRecord, "days": list|None}。"""
    if not valid_coords(lat, lng):
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, "经纬度非法"), "days": None}
    params = {
        "latitude": lat,
        "longitude": lng,
        "daily": "shortwave_radiation_sum,precipitation_sum,wind_speed_10m_max,cloud_cover_mean,temperature_2m_max,temperature_2m_min",
        "forecast_days": 3,
        "timezone": "Asia/Shanghai",
        "wind_speed_unit": "ms",
    }
    data, err = await fetch_json(FORECAST_URL, params, source=SOURCE, data_kind=DATA_KIND)
    if err:
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, err), "days": None}
    daily = (data or {}).get("daily") or {}
    days = sanitize_days(_daily_to_raw_days(daily))
    if not days:
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, "接口返回但无有效数据（校验后为空）"), "days": None}
    record = make_record(
        source=SOURCE,
        data_type=DATA_TYPE,
        data_kind=DATA_KIND,
        latitude=lat,
        longitude=lng,
        value={"days": len(days), "irradiance": [d["irradiance"] for d in days], "wind_max": max(d["wind"] for d in days)},
        unit=UNITS,
        valid_time=f"{days[0]['date']} ~ {days[-1]['date']}",
    )
    return {"record": record, "days": days}