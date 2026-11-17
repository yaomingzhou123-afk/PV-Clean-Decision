import asyncio

from data_sources.models import now_iso, simulation_record
from data_sources.open_meteo_air import get_air
from data_sources.open_meteo_forecast import _daily_to_raw_days, get_forecast, sanitize_days
from data_sources.pvgis_source import get_pvgis

FALLBACK_FORECAST = {
    "days": [
        {"date": "样例 D1", "irradiance": 2.9, "rain": 0.0, "wind": 9.5, "cloud": 15, "temp_max": None, "temp_min": None},
        {"date": "样例 D2", "irradiance": 3.1, "rain": 0.0, "wind": 11.0, "cloud": 10, "temp_max": None, "temp_min": None},
        {"date": "样例 D3", "irradiance": 2.4, "rain": 0.8, "wind": 14.0, "cloud": 45, "temp_max": None, "temp_min": None},
    ],
    "source": "fallback",
}

FALLBACK_AIR = {"pm10": 86.0, "dust": 80.0, "source": "fallback"}

DEMO_FORECAST = {
    "days": [
        {"date": "演示 D1", "irradiance": 5.9, "rain": 0.0, "wind": 8.0, "cloud": 5, "temp_max": None, "temp_min": None},
        {"date": "演示 D2", "irradiance": 6.1, "rain": 0.0, "wind": 9.0, "cloud": 4, "temp_max": None, "temp_min": None},
        {"date": "演示 D3", "irradiance": 5.4, "rain": 0.0, "wind": 11.0, "cloud": 8, "temp_max": None, "temp_min": None},
    ],
    "source": "demo",
}

DEMO_AIR = {"pm10": 135.0, "dust": 120.0, "source": "demo"}

FORECAST_UNITS = {"irradiance": "kWh/m²", "rain": "mm", "wind": "m/s", "cloud": "%", "temp_max": "°C", "temp_min": "°C"}
AIR_UNITS = {"pm10": "μg/m³", "pm2_5": "μg/m³", "dust": "μg/m³"}


def demo_context() -> dict:
    """演示模式：完全离线，全部数据为 simulation，显式标注，不伪装成任何真实接口数据。"""
    records = [
        simulation_record("demo-builtin", "weather_forecast", 44.01, 87.31, DEMO_FORECAST, FORECAST_UNITS, "演示 3 天"),
        simulation_record("demo-builtin", "air_quality_forecast", 44.01, 87.31, DEMO_AIR, AIR_UNITS, "演示 48 小时"),
    ]
    return {
        "forecast": {**DEMO_FORECAST, "fetched_at": now_iso(), "quality": "demo"},
        "air": {**DEMO_AIR, "fetched_at": now_iso(), "quality": "demo"},
        "theoretical": None,
        "quality": "demo",
        "fetched_at": now_iso(),
        "data_source_records": records,
    }


async def fetch_context(lat: float, lng: float, loss_pct: float = 10.0) -> dict:
    """聚合三个官方数据源（天气预报 / 空气质量预报 / PVGIS 历史气候）。
    单源失败时该源降级为内置样例并追加 simulation 记录（显式标注，不伪装）；
    每条数据的元数据见 data_source_records。"""
    f, a, p = await asyncio.gather(
        get_forecast(lat, lng),
        get_air(lat, lng),
        get_pvgis(lat, lng, loss_pct),
    )
    records = [f["record"], a["record"], p["record"]]

    if f["days"]:
        forecast = {"days": f["days"], "source": "open-meteo", "fetched_at": f["record"]["fetched_at"], "quality": "live"}
    else:
        forecast = {**FALLBACK_FORECAST, "fetched_at": now_iso(), "quality": "fallback"}
        records.append(
            simulation_record("fallback-builtin", "weather_forecast", lat, lng, FALLBACK_FORECAST, FORECAST_UNITS, "预报接口失败，降级样例")
        )

    if a["air"]:
        air = {**a["air"], "source": "open-meteo-air", "fetched_at": a["record"]["fetched_at"], "quality": "live"}
    else:
        air = {**FALLBACK_AIR, "fetched_at": now_iso(), "quality": "fallback"}
        records.append(
            simulation_record("fallback-builtin", "air_quality_forecast", lat, lng, FALLBACK_AIR, AIR_UNITS, "空气质量接口失败，降级样例")
        )

    theoretical = p["pvgis"] if p["pvgis"] else None

    live_sources = sum(1 for x in (forecast.get("quality"), air.get("quality")) if x == "live") + (1 if theoretical else 0)
    if live_sources == 3:
        quality = "live-good"
    elif live_sources >= 1:
        quality = "live-degraded"
    else:
        quality = "fallback"

    return {
        "forecast": forecast,
        "air": air,
        "theoretical": theoretical,
        "quality": quality,
        "fetched_at": now_iso(),
        "data_source_records": records,
    }