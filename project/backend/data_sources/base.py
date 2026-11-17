import asyncio
import os
import time

import httpx

from data_sources.health import update_health
from data_sources.models import now_iso

DS_TIMEOUT = float(os.getenv("DS_TIMEOUT", "10"))
DS_RETRIES = max(1, int(os.getenv("DS_RETRIES", "2")))
DS_CACHE_TTL = int(os.getenv("DS_CACHE_TTL", "21600"))

_cache: dict = {}


def valid_coords(lat: float, lng: float) -> bool:
    try:
        lat_f, lng_f = float(lat), float(lng)
    except (TypeError, ValueError):
        return False
    return -90 <= lat_f <= 90 and -180 <= lng_f <= 180


async def fetch_json(url: str, params: dict, source: str, data_kind: str, timeout: float | None = None, retries: int | None = None) -> tuple[dict | None, str | None]:
    """带超时与有限重试的 JSON GET。成功返回 (data, None)，失败返回 (None, 错误信息)。"""
    effective_timeout = timeout or DS_TIMEOUT
    effective_retries = retries if retries is not None else DS_RETRIES
    last_error = None
    for attempt in range(effective_retries):
        t0 = time.time()
        try:
            async with httpx.AsyncClient(headers={"User-Agent": "pv-agent"}) as client:
                resp = await client.get(url, params=params, timeout=effective_timeout)
                resp.raise_for_status()
                data = resp.json()
            update_health(source, status="ok", latency_ms=round((time.time() - t0) * 1000, 1), data_kind=data_kind)
            return data, None
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            update_health(source, status="error", latency_ms=round((time.time() - t0) * 1000, 1), error=last_error, data_kind=data_kind)
            if attempt < effective_retries - 1:
                await asyncio.sleep(0.6 * (attempt + 1))
    return None, last_error


def cache_key(source: str, **params) -> str:
    parts = [source] + [f"{k}={round(v, 4) if isinstance(v, float) else v}" for k, v in sorted(params.items())]
    return "|".join(parts)


def cache_get(key: str) -> dict | None:
    entry = _cache.get(key)
    if not entry:
        return None
    record, expires_at = entry
    if time.time() >= expires_at:
        _cache.pop(key, None)
        return None
    cached_record = dict(record)
    cached_record["is_cached"] = True
    cached_record["status"] = "cached"
    return cached_record


def cache_set(key: str, record: dict, ttl: int | None = None) -> None:
    _cache[key] = (record, time.time() + (ttl or DS_CACHE_TTL))


def cache_clear() -> None:
    _cache.clear()