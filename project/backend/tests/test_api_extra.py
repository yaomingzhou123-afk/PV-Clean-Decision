"""V3.0 第七阶段：新增 REST 接口与统一错误处理的工程测试。"""

import json

import pytest
from fastapi.testclient import TestClient

import main as main_module
from data_sources.models import make_record


@pytest.fixture()
def client():
    return TestClient(main_module.app)


@pytest.fixture()
def temp_config(tmp_path, monkeypatch):
    """把站点配置指向临时文件，避免测试污染真实 pv_config.json。"""
    original = json.loads(main_module.CONFIG_PATH.read_text(encoding="utf-8"))
    tmp = tmp_path / "pv_config.json"
    tmp.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(main_module, "CONFIG_PATH", tmp)
    yield tmp
    tmp.unlink(missing_ok=True)


def test_health_returns_version_and_mcp_flag(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["mode"] in ("llm", "rule")
    assert "version" in data
    assert "mcp_enabled" in data


def test_config_and_site_config_are_consistent(client):
    a = client.get("/api/config").json()
    b = client.get("/api/site/config").json()
    assert a["site"]["name"] == b["site"]["name"]


def test_site_config_update_writes_whitelist_fields(client, temp_config):
    resp = client.put("/api/site/config", json={"name": "测试电站", "capacity_mw": 30})
    assert resp.status_code == 200
    data = resp.json()
    assert data["site"]["name"] == "测试电站"
    assert data["site"]["capacity_mw"] == 30
    saved = json.loads(temp_config.read_text(encoding="utf-8"))
    assert saved["site"]["name"] == "测试电站"


def test_site_config_update_rejects_unknown_field(client, temp_config):
    resp = client.put("/api/site/config", json={"no_such_field": 1})
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_site_config_update_rejects_empty_body(client, temp_config):
    resp = client.put("/api/site/config", json={})
    assert resp.status_code == 400


def test_site_config_update_validates_range(client, temp_config):
    resp = client.put("/api/site/config", json={"capacity_mw": 99999})
    assert resp.status_code == 422


def test_data_sources_health_endpoint(client):
    resp = client.get("/api/data-sources/health")
    assert resp.status_code == 200
    assert "sources" in resp.json()


def _fake_record(source, data_kind="forecast", status="ok"):
    return make_record(
        source=source,
        data_type="weather_forecast",
        data_kind=data_kind,
        latitude=44.01,
        longitude=87.31,
        value={"days": []},
        unit={"irradiance": "kWh/m²"},
        valid_time="测试",
        status=status,
        error_message=None if status == "ok" else "测试错误",
    )


def test_weather_endpoint_ok(client, monkeypatch):
    async def fake_forecast(lat, lng):
        return {"days": [{"date": "D1", "irradiance": 5.8, "rain": 0, "wind": 9, "cloud": 0}], "record": _fake_record("open-meteo")}
    monkeypatch.setattr(main_module, "get_forecast", fake_forecast)
    resp = client.get("/api/weather", params={"lat": 44.01, "lng": 87.31})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["days"]) == 1


def test_weather_endpoint_source_failure_is_not_disguised(client, monkeypatch):
    async def fake_forecast(lat, lng):
        return {"days": [], "record": _fake_record("open-meteo", status="error")}
    monkeypatch.setattr(main_module, "get_forecast", fake_forecast)
    resp = client.get("/api/weather", params={"lat": 44.01, "lng": 87.31})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert data["error_message"]


def test_weather_endpoint_rejects_invalid_coords(client):
    resp = client.get("/api/weather", params={"lat": 999, "lng": 87.31})
    assert resp.status_code == 422


def test_air_endpoint(client, monkeypatch):
    async def fake_air(lat, lng):
        return {"air": {"pm10": 135.0, "pm2_5": 24.0}, "record": _fake_record("open-meteo-air", "user_input")}
    monkeypatch.setattr(main_module, "get_air", fake_air)
    resp = client.get("/api/air", params={"lat": 44.01, "lng": 87.31})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_pv_theoretical_endpoint(client, monkeypatch):
    async def fake_pvgis(lat, lng, loss_pct=10.0):
        return {"pvgis": {"E_d": 3.79, "month": 11}, "record": _fake_record("pvgis", "historical")}
    monkeypatch.setattr(main_module, "get_pvgis", fake_pvgis)
    resp = client.get("/api/pv/theoretical", params={"lat": 44.01, "lng": 87.31, "loss_pct": 10})
    assert resp.status_code == 200
    assert resp.json()["pvgis"]["E_d"] == 3.79


def test_soiling_estimate_endpoint(client):
    resp = client.post("/api/soiling/estimate", json={"pm10": 135, "pm2_5": 24, "days_since_clean": 20})
    assert resp.status_code == 200
    data = resp.json()
    assert data["result_kind"] == "model_estimate"
    assert data["soiling"]["loss_pct"] is not None
    assert data["soiling"]["method"] == "model_estimate"
    assert data["soiling"]["pm2_5"] == 24


def test_soiling_estimate_rejects_invalid(client):
    resp = client.post("/api/soiling/estimate", json={"pm10": 9999})
    assert resp.status_code == 422


def test_economics_analyze_demo(client):
    resp = client.post("/api/economics/analyze", json={"scenario": "demo"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["result_kind"] == "model_estimate"
    assert data["metrics"]["decision"]["action"] is not None
    assert data["metrics"]["economics"]["net_gain"] is not None


def test_economics_analyze_with_sensitivity(client):
    resp = client.post("/api/economics/analyze", json={"scenario": "demo", "include_sensitivity": True})
    assert resp.status_code == 200
    assert resp.json()["metrics"]["sensitivity"] is not None


def test_economics_analyze_rejects_invalid(client):
    resp = client.post("/api/economics/analyze", json={"capacity_mw": 0.1})
    assert resp.status_code == 422


def test_unified_error_format_has_code_field(client):
    resp = client.post("/api/economics/analyze", json={"capacity_mw": 0.1})
    body = resp.json()
    assert resp.status_code == 422
    assert body.get("code") == "validation_error"
    assert isinstance(body.get("detail"), list)


def test_soiling_metrics_include_pm25(client):
    resp = client.post("/api/economics/analyze", json={"scenario": "demo"})
    soiling = resp.json()["metrics"]["soiling"]
    assert "pm2_5" in soiling
