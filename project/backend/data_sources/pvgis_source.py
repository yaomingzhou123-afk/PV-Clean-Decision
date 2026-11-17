from datetime import datetime, timezone

from data_sources.base import cache_get, cache_key, cache_set, fetch_json, valid_coords
from data_sources.models import error_record, make_record

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
SOURCE = "pvgis"
DATA_TYPE = "solar_resource_historical"
DATA_KIND = "historical"

UNITS = {"E_d": "kWh/kWp", "E_m": "kWh/kWp/month", "H(i)_m": "kWh/m²/month"}


def _current_month() -> int:
    return datetime.now(timezone.utc).astimezone().month


def _parse_e_d(data: dict) -> dict | None:
    monthly = (data.get("outputs") or {}).get("monthly") or {}
    fixed = monthly.get("fixed") or []
    if not fixed:
        return None
    month = _current_month()
    entry = next((m for m in fixed if m.get("month") == month), None) or fixed[0]
    e_d = entry.get("E_d")
    if not isinstance(e_d, (int, float)) or e_d <= 0:
        return None
    meteo = (data.get("inputs") or {}).get("meteo_data") or {}
    return {
        "E_d": round(float(e_d), 2),
        "month": entry.get("month"),
        "radiation_db": meteo.get("radiation_db"),
        "year_min": meteo.get("year_min"),
        "year_max": meteo.get("year_max"),
    }


async def get_pvgis(lat: float, lng: float, loss_pct: float = 10.0) -> dict:
    """获取指定经纬度的月均理论发电量 E_d（PVGIS-ERA5，2005–2023 历史气候均值，非实时数据）。
    结果缓存 6 小时；命中缓存时 is_cached=True 且保留原始 fetched_at。
    返回 {"record": DataRecord, "pvgis": dict|None}。"""
    if not valid_coords(lat, lng):
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, "经纬度非法"), "pvgis": None}
    key = cache_key(SOURCE, lat=lat, lng=lng, loss=loss_pct)
    cached = cache_get(key)
    if cached:
        return {"record": cached, "pvgis": cached["value"]}
    params = {
        "lat": lat,
        "lon": lng,
        "peakpower": 1,
        "loss": loss_pct,
        "angle": 35,
        "aspect": 0,
        "outputformat": "json",
    }
    data, err = await fetch_json(PVGIS_URL, params, source=SOURCE, data_kind=DATA_KIND, timeout=12)
    if err:
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, err), "pvgis": None}
    pvgis = _parse_e_d(data or {})
    if not pvgis:
        return {"record": error_record(SOURCE, DATA_TYPE, DATA_KIND, lat, lng, "接口返回但无有效 E_d"), "pvgis": None}
    record = make_record(
        source=SOURCE,
        data_type=DATA_TYPE,
        data_kind=DATA_KIND,
        latitude=lat,
        longitude=lng,
        value=pvgis,
        unit=UNITS,
        valid_time=f"month={pvgis['month']}（{pvgis.get('year_min')}–{pvgis.get('year_max')} 历史均值）",
    )
    cache_set(key, record)
    return {"record": record, "pvgis": pvgis}