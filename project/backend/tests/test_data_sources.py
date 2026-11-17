import asyncio

import httpx as _httpx

from data_sources import base
from data_sources import health as ds_health
from data_sources.models import make_record
from data_sources.nasa_power import get_nasa_daily
from data_sources.open_meteo_air import get_air
from data_sources.open_meteo_forecast import get_forecast
from data_sources.pvgis_source import get_pvgis

_REAL_ASYNC_CLIENT = _httpx.AsyncClient


def run(coro):
    return asyncio.run(coro)


def fake_json(data):
    async def _f(url, params, source, data_kind, timeout=None, retries=None):
        return data, None

    return _f


def fake_error(msg="ConnectTimeout"):
    async def _f(url, params, source, data_kind, timeout=None, retries=None):
        return None, msg

    return _f


FORECAST_PAYLOAD = {
    "daily": {
        "time": ["2026-11-15"],
        "shortwave_radiation_sum": [18.0],
        "precipitation_sum": [0.0],
        "wind_speed_10m_max": [10.0],
        "cloud_cover_mean": [10],
        "temperature_2m_max": [5.0],
        "temperature_2m_min": [-2.0],
    }
}

AIR_PAYLOAD = {
    "hourly": {
        "time": ["2026-11-15T00:00", "2026-11-15T01:00"],
        "pm10": [20.0, 22.0],
        "pm2_5": [10.0, 11.0],
        "dust": [0.0, 1.0],
    }
}

PVGIS_PAYLOAD = {
    "inputs": {"meteo_data": {"radiation_db": "PVGIS-ERA5", "year_min": 2005, "year_max": 2023}},
    "outputs": {"monthly": {"fixed": [{"month": 11, "E_d": 3.79}]}},
}


def test_forecast_ok_with_unit_conversion(monkeypatch):
    monkeypatch.setattr("data_sources.open_meteo_forecast.fetch_json", fake_json(FORECAST_PAYLOAD))
    out = run(get_forecast(44.01, 87.31))
    assert out["record"]["status"] == "ok"
    assert out["record"]["data_kind"] == "forecast"
    assert out["record"]["is_simulated"] is False
    assert out["days"][0]["irradiance"] == 5.0
    assert out["days"][0]["wind"] == 10.0
    assert out["days"][0]["temp_max"] == 5.0


def test_forecast_timeout_returns_error_not_simulation(monkeypatch):
    monkeypatch.setattr("data_sources.open_meteo_forecast.fetch_json", fake_error("ConnectTimeout"))
    out = run(get_forecast(44.01, 87.31))
    assert out["record"]["status"] == "error"
    assert out["days"] is None
    assert out["record"]["is_simulated"] is False
    assert "ConnectTimeout" in out["record"]["error_message"]


def test_forecast_empty_payload_is_error(monkeypatch):
    monkeypatch.setattr("data_sources.open_meteo_forecast.fetch_json", fake_json({"daily": {}}))
    out = run(get_forecast(44.01, 87.31))
    assert out["record"]["status"] == "error"
    assert out["days"] is None


def test_forecast_invalid_coords_rejected():
    out = run(get_forecast(999.0, 999.0))
    assert out["record"]["status"] == "error"
    assert "经纬度" in out["record"]["error_message"]


def test_air_ok_forecast_kind(monkeypatch):
    monkeypatch.setattr("data_sources.open_meteo_air.fetch_json", fake_json(AIR_PAYLOAD))
    out = run(get_air(44.01, 87.31))
    assert out["record"]["status"] == "ok"
    assert out["record"]["data_type"] == "air_quality_forecast"
    assert out["air"]["pm10"] == 21.0
    assert out["air"]["dust"] == 0.5


def test_air_failure_is_error(monkeypatch):
    monkeypatch.setattr("data_sources.open_meteo_air.fetch_json", fake_error("HTTP 500"))
    out = run(get_air(44.01, 87.31))
    assert out["record"]["status"] == "error"
    assert out["air"] is None


def test_pvgis_ok_historical_kind(monkeypatch):
    base.cache_clear()
    monkeypatch.setattr("data_sources.pvgis_source.fetch_json", fake_json(PVGIS_PAYLOAD))
    out = run(get_pvgis(44.01, 87.31, 10.0))
    assert out["record"]["status"] == "ok"
    assert out["record"]["data_kind"] == "historical"
    assert out["pvgis"]["E_d"] == 3.79


def test_pvgis_cache_hit_preserves_fetched_at(monkeypatch):
    base.cache_clear()
    monkeypatch.setattr("data_sources.pvgis_source.fetch_json", fake_json(PVGIS_PAYLOAD))
    first = run(get_pvgis(44.01, 87.31, 10.0))
    original_fetched_at = first["record"]["fetched_at"]

    monkeypatch.setattr("data_sources.pvgis_source.fetch_json", fake_error("不应再次请求"))
    second = run(get_pvgis(44.01, 87.31, 10.0))
    assert second["record"]["is_cached"] is True
    assert second["record"]["status"] == "cached"
    assert second["record"]["fetched_at"] == original_fetched_at
    assert second["pvgis"]["E_d"] == 3.79


def test_cache_expired_refetches(monkeypatch):
    base.cache_clear()
    record = make_record(
        source="pvgis", data_type="solar_resource_historical", data_kind="historical",
        latitude=44.01, longitude=87.31, value={"E_d": 1.0}, unit={}, valid_time="m=11",
    )
    base.cache_set("expired-key", record, ttl=-1)
    assert base.cache_get("expired-key") is None


def test_nasa_disabled_returns_error():
    out = run(get_nasa_daily(44.01, 87.31, "20261101", "20261110"))
    assert out["record"]["status"] == "error"
    assert "未启用" in out["record"]["error_message"]


def patch_transport(monkeypatch, handler):
    def factory(**kwargs):
        kwargs.pop("headers", None)
        kwargs.pop("timeout", None)
        return _REAL_ASYNC_CLIENT(transport=_httpx.MockTransport(handler))

    monkeypatch.setattr("data_sources.base.httpx.AsyncClient", factory)


def test_health_records_error_status(monkeypatch):
    ds_health.reset_health()

    def handler(request):
        raise _httpx.ConnectTimeout("timeout")

    patch_transport(monkeypatch, handler)
    out = run(get_forecast(44.01, 87.31))
    assert out["record"]["status"] == "error"
    statuses = {h["source"]: h["status"] for h in ds_health.get_health()}
    assert statuses.get("open-meteo-forecast") == "error"


def test_health_records_ok_status(monkeypatch):
    ds_health.reset_health()

    def handler(request):
        return _httpx.Response(200, json=FORECAST_PAYLOAD)

    patch_transport(monkeypatch, handler)
    out = run(get_forecast(44.01, 87.31))
    assert out["record"]["status"] == "ok"
    statuses = {h["source"]: h["status"] for h in ds_health.get_health()}
    assert statuses.get("open-meteo-forecast") == "ok"