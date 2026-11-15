import os

from data_sources.base import fetch_json, valid_coords
from data_sources.models import error_record, make_record

NASA_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
SOURCE = "nasa-power"
DATA_TYPE = "solar_resource_historical"
DATA_KIND = "historical"

UNITS = {"irradiance": "kWh/m²/day", "temp_max": "°C", "temp_min": "°C"}

NASA_POWER_ENABLED = os.getenv("NASA_POWER_ENABLED", "0") == "1"


def _parse_daily(data: dict) -> list | None:
    props = (data or {}).get("properties") or {}
    param = props.get("parameter") or {}
    irr = param.get("ALLSKY_SFC_SW_DWN") or {}
    tmax = param.get("T2M_MAX") or {}
    tmin = param.get("T2M_MIN") or {}
    days = []
    for date_str, value in sorted(irr.items()):
        if value is None or value == -999:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue
        if v < 0 or v > 40:
            continue
        t_mx = tmax.get(date_str)
        t_mn = tmin.get(date_str)
        days.append(
            {
                "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                "irradiance": round(v, 2),
                "temp_max": round(float(t_mx), 1) if isinstance(t_mx, (int, float)) and t_mx != -999 else None,
                "temp_min": round(float(t_mn), 1) if isinstance(t_mn, (int, float)) and t_mn != -999 else None,
            }
        )
    return days or None


async def get_nasa_daily(lat: float, lng: float, start: str, end: str) -> dict:
    """获取 NASA POWER 逐日历史辐照与温度（再分析数据，非实时；单位 kWh/m²/day，无需转换）。
    默认关闭，需设置 NASA_POWER_ENABLED=1 启用。
    start/end 格式 YYYYMMDD。返回 {"record": DataRecord, "days": list|None}。"""
    if not NASA_POWER_ENABLED:
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, "未启用（设置 NASA_POWER_ENABLED=1 开启）"), "days": None}
    if not valid_coords(lat, lng):
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, "经纬度非法"), "days": None}
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,T2M_MAX,T2M_MIN",
        "community": "RE",
        "latitude": lat,
        "longitude": lng,
        "start": start,
        "end": end,
        "format": "JSON",
    }
    data, err = await fetch_json(NASA_URL, params, source=SOURCE, data_kind=DATA_KIND, timeout=15)
    if err:
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, err), "days": None}
    days = _parse_daily(data)
    if not days:
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, "接口返回但无有效数据"), "days": None}
    record = make_record(
        source=SOURCE,
        data_type=DATA_TYPE,
        data_kind=DATA_KIND,
        latitude=lat,
        longitude=lng,
        value={"days": len(days), "irradiance": [d["irradiance"] for d in days]},
        unit=UNITS,
        valid_time=f"{days[0]['date']} ~ {days[-1]['date']}",
    )
    return {"record": record, "days": days}