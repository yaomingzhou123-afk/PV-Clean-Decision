import asyncio
from datetime import datetime, timezone

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"

PVGIS_CACHE_TTL_SECONDS = 6 * 3600
_pvgis_cache: dict = {}

FALLBACK_FORECAST = {
    "days": [
        {"date": "样例 D1", "irradiance": 2.9, "rain": 0.0, "wind": 9.5, "cloud": 15},
        {"date": "样例 D2", "irradiance": 3.1, "rain": 0.0, "wind": 11.0, "cloud": 10},
        {"date": "样例 D3", "irradiance": 2.4, "rain": 0.8, "wind": 14.0, "cloud": 45},
    ],
    "source": "fallback",
}

FALLBACK_AIR = {"pm10": 86.0, "dust": 80.0, "source": "fallback"}

DEMO_FORECAST = {
    "days": [
        {"date": "演示 D1", "irradiance": 5.9, "rain": 0.0, "wind": 8.0, "cloud": 5},
        {"date": "演示 D2", "irradiance": 6.1, "rain": 0.0, "wind": 9.0, "cloud": 4},
        {"date": "演示 D3", "irradiance": 5.4, "rain": 0.0, "wind": 11.0, "cloud": 8},
    ],
    "source": "demo",
}

DEMO_AIR = {"pm10": 135.0, "dust": 120.0, "source": "demo"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sanitize_days(raw_days: list) -> list | None:
    days = []
    for d in raw_days or []:
        try:
            irr = d.get("irradiance")
            if irr is None or not isinstance(irr, (int, float)) or irr < 0 or irr > 12:
                continue
            rain = d.get("rain")
            wind = d.get("wind")
            cloud = d.get("cloud")
            days.append(
                {
                    "date": str(d.get("date", "")),
                    "irradiance": round(float(irr), 2),
                    "rain": round(float(rain), 1) if isinstance(rain, (int, float)) and rain >= 0 else 0.0,
                    "wind": round(float(wind), 1) if isinstance(wind, (int, float)) and wind >= 0 else 0.0,
                    "cloud": round(float(cloud), 0) if isinstance(cloud, (int, float)) and 0 <= cloud <= 100 else 0.0,
                }
            )
        except (TypeError, AttributeError):
            continue
    return days or None


def demo_context() -> dict:
    return {
        "forecast": {**DEMO_FORECAST, "fetched_at": now_iso(), "quality": "demo"},
        "air": {**DEMO_AIR, "fetched_at": now_iso(), "quality": "demo"},
        "theoretical": None,
        "quality": "demo",
        "fetched_at": now_iso(),
    }


async def _get(client: httpx.AsyncClient, url: str, params: dict, timeout: float = 8.0) -> dict | None:
    for attempt in range(2):
        try:
            resp = await client.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt == 0:
                await asyncio.sleep(0.6)
    return None


async def fetch_forecast(lat: float, lng: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lng,
        "daily": "shortwave_radiation_sum,precipitation_sum,wind_speed_10m_max,cloud_cover_mean",
        "forecast_days": 3,
        "timezone": "Asia/Shanghai",
    }
    async with httpx.AsyncClient(headers={"User-Agent": "pv-agent"}) as client:
        data = await _get(client, FORECAST_URL, params)
    if not data or "daily" not in data:
        return {**FALLBACK_FORECAST, "fetched_at": now_iso(), "quality": "fallback"}
    daily = data["daily"]
    time_list = daily.get("time") or []
    raw_days = []
    for i, day in enumerate(time_list):
        raw_days.append(
            {
                "date": day,
                "irradiance": (daily.get("shortwave_radiation_sum") or [None] * len(time_list))[i],
                "rain": (daily.get("precipitation_sum") or [None] * len(time_list))[i],
                "wind": (daily.get("wind_speed_10m_max") or [None] * len(time_list))[i],
                "cloud": (daily.get("cloud_cover_mean") or [None] * len(time_list))[i],
            }
        )
    days = sanitize_days(raw_days)
    if not days:
        return {**FALLBACK_FORECAST, "fetched_at": now_iso(), "quality": "fallback"}
    return {"days": days, "source": "open-meteo", "fetched_at": now_iso(), "quality": "live"}


async def fetch_air(lat: float, lng: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lng,
        "hourly": "pm10,pm2_5,dust",
        "forecast_days": 2,
        "timezone": "Asia/Shanghai",
    }
    async with httpx.AsyncClient(headers={"User-Agent": "pv-agent"}) as client:
        data = await _get(client, AIR_URL, params)
    if not data or "hourly" not in data:
        return {**FALLBACK_AIR, "fetched_at": now_iso(), "quality": "fallback"}
    hourly = data["hourly"]
    pm10 = [v for v in hourly.get("pm10", []) if isinstance(v, (int, float)) and 0 <= v <= 1000]
    dust = [v for v in hourly.get("dust", []) if isinstance(v, (int, float)) and 0 <= v <= 2000]
    if not pm10:
        return {**FALLBACK_AIR, "fetched_at": now_iso(), "quality": "fallback"}
    return {
        "pm10": round(sum(pm10) / len(pm10), 1),
        "dust": round(sum(dust) / len(dust), 1) if dust else FALLBACK_AIR["dust"],
        "source": "open-meteo-air",
        "fetched_at": now_iso(),
        "quality": "live",
    }


async def fetch_pvgis_theoretical(lat: float, lng: float, loss_pct: float) -> dict | None:
    key = (round(lat, 2), round(lng, 2), round(loss_pct, 1))
    cached = _pvgis_cache.get(key)
    if cached:
        age = datetime.now(timezone.utc).timestamp() - cached["cached_at"]
        if age < PVGIS_CACHE_TTL_SECONDS:
            return {**cached["data"], "cached": True}
    params = {
        "lat": lat,
        "lon": lng,
        "peakpower": 1,
        "loss": loss_pct,
        "angle": 35,
        "aspect": 0,
        "outputformat": "json",
    }
    async with httpx.AsyncClient(headers={"User-Agent": "pv-agent"}) as client:
        data = await _get(client, PVGIS_URL, params, timeout=12.0)
    if not data or "outputs" not in data:
        return None
    monthly = (data.get("outputs") or {}).get("monthly") or {}
    fixed = monthly.get("fixed") or []
    current_month = datetime.now(timezone.utc).astimezone().month
    entry = next((m for m in fixed if m.get("month") == current_month), None)
    if not entry:
        entry = fixed[0] if fixed else None
    e_d = entry.get("E_d") if entry else None
    if not isinstance(e_d, (int, float)) or e_d <= 0:
        return None
    result = {
        "E_d": round(float(e_d), 2),
        "month": entry.get("month"),
        "radiation_db": (data.get("inputs") or {}).get("meteo_data", {}).get("radiation_db"),
        "year_min": (data.get("inputs") or {}).get("meteo_data", {}).get("year_min"),
        "year_max": (data.get("inputs") or {}).get("meteo_data", {}).get("year_max"),
        "source": "pvgis",
        "fetched_at": now_iso(),
        "cached": False,
    }
    _pvgis_cache[key] = {"data": result, "cached_at": datetime.now(timezone.utc).timestamp()}
    return result


async def fetch_context(lat: float, lng: float, loss_pct: float = 10.0) -> dict:
    forecast, air, theoretical = await asyncio.gather(
        fetch_forecast(lat, lng),
        fetch_air(lat, lng),
        fetch_pvgis_theoretical(lat, lng, loss_pct),
    )
    live_sources = sum(
        1 for x in (forecast.get("quality"), air.get("quality")) if x == "live"
    ) + (1 if theoretical else 0)
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
    }