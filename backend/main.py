import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Literal

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from env_loader import load_env

load_env()

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

import llm
from agent_loop import stream_agent
from data_sources.health import get_health
from data_sources.open_meteo_air import get_air
from data_sources.open_meteo_forecast import get_forecast
from data_sources.pvgis_source import get_pvgis
from orchestrator import CONFIG_PATH, load_config, stream_decision
from pv_model import compute_metrics, estimate_soiling, validate_config
from simulation_lab import calculate as calculate_simulation
from simulation_lab import defaults_payload as simulation_defaults_payload
from weather import demo_context, fetch_context

ROOT = BASE_DIR.parent
FRONTEND = ROOT / "frontend"

APP_VERSION = "3.0.7"

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("pv.api")

app = FastAPI(
    title="光伏电站沙尘清洗决策 Agent",
    version=APP_VERSION,
    description=(
        "疆光 · 清洗决策驾驶舱后端。"
        "所有收益与污损结果均为模型估算；demo/simulation 模式的数据为内置样例，不代表真实电站运行数据。"
    ),
)


# ---------------------------------------------------------------------------
# 请求日志与统一错误响应
# ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000
    path = request.url.path
    if path.startswith("/static"):
        return response
    logger.info(
        "%s %s -> %s (%.1f ms)",
        request.method,
        path,
        response.status_code,
        elapsed,
    )
    return response


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning("参数错误 %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=400, content={"detail": str(exc), "code": "invalid_params"})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    logger.warning("校验失败 %s %s: %s", request.method, request.url.path, exc.errors()[:3])
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "code": "validation_error"},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请查看后端日志", "code": "internal_error"},
    )


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class DecisionRequest(BaseModel):
    capacity_mw: float = Field(ge=0.5, le=5000, description="装机容量 MW")
    days_since_clean: int = Field(ge=0, le=365, description="距上次清洗天数")
    price_per_kwh: float = Field(ge=0.05, le=2.0, description="上网电价 元/kWh")
    cleaning_cost: float = Field(ge=0, le=10_000_000, description="清洗成本 元/次")
    scenario: Literal["demo", "live"] = "demo"


class AgentRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500, description="自然语言问题")
    capacity_mw: float = Field(default=20, ge=0.5, le=5000)
    days_since_clean: int = Field(default=20, ge=0, le=365)
    price_per_kwh: float = Field(default=0.25, ge=0.05, le=2.0)
    cleaning_cost: float = Field(default=4000, ge=0, le=10_000_000)
    scenario: Literal["demo", "live"] = "demo"


class SimulationRequest(BaseModel):
    """模拟实验室输入。所有字段都是用户假设，不是真实电站数据。"""

    pm10: float = Field(default=80, ge=0, le=2000, description="PM10 μg/m³")
    pm2_5: float = Field(default=24, ge=0, le=1000, description="PM2.5 μg/m³")
    dry_days: int = Field(default=20, ge=0, le=365, description="连续无有效降雨天数")
    soiling_override_pct: float | None = Field(default=None, ge=0, le=30, description="可选污损手动假设 %")
    capacity_mw: float = Field(default=20, ge=0.5, le=5000, description="装机容量 MW")
    tilt_angle_deg: float = Field(default=35, ge=0, le=60, description="组件倾角 °")
    price_per_kwh: float = Field(default=0.25, ge=0.05, le=2.0, description="上网电价 元/kWh")
    labor_cost: float = Field(default=2000, ge=0, le=100000, description="人工成本 元/次")
    water_cost: float = Field(default=1000, ge=0, le=100000, description="用水成本 元/次")
    equipment_cost: float = Field(default=1000, ge=0, le=100000, description="设备及其他成本 元/次")
    expected_rain_mm: float = Field(default=0, ge=0, le=200, description="预计未来降雨 mm")
    wind_speed_ms: float = Field(default=9, ge=0, le=60, description="风速 m/s")
    recovery_efficiency: float = Field(default=0.95, ge=0.5, le=1.0, description="清洗恢复效率")
    avg_irradiance_kwh_m2_day: float = Field(default=5.8, ge=0.5, le=10, description="示例日辐照 kWh/m²/日")
    horizon_days: int = Field(default=30, ge=7, le=90, description="评价周期 天")
    fixed_cycle_days: int = Field(default=30, ge=7, le=90, description="固定周期策略间隔 天")
    soiling_threshold_pct: float = Field(default=5, ge=1, le=15, description="污损阈值 %")
    scenario_name: str | None = Field(default=None, max_length=80, description="模拟场景名称")


class SiteConfigUpdate(BaseModel):
    """电站参数管理：仅允许更新白名单字段，全部写入 pv_config.json。"""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=60)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    capacity_mw: float | None = Field(default=None, ge=0.5, le=5000)
    days_since_clean: int | None = Field(default=None, ge=0, le=365)
    price_per_kwh: float | None = Field(default=None, ge=0.05, le=2.0)
    cleaning_cost: float | None = Field(default=None, ge=0, le=10_000_000)
    labor_cost: float | None = Field(default=None, ge=0, le=10_000_000)
    water_cost: float | None = Field(default=None, ge=0, le=10_000_000)
    equipment_cost: float | None = Field(default=None, ge=0, le=10_000_000)
    efficiency: float | None = Field(default=None, gt=0, le=1)
    recovery_efficiency: float | None = Field(default=None, ge=0.5, le=1)
    horizon_days: int | None = Field(default=None, ge=1, le=365)
    downtime_hours: float | None = Field(default=None, ge=0, le=48)
    base_rate_per_day: float | None = Field(default=None, ge=0, le=0.05)
    pm10_ref: float | None = Field(default=None, ge=0, le=1000)
    pm10_factor: float | None = Field(default=None, ge=0, le=0.01)
    max_loss: float | None = Field(default=None, gt=0, le=1)
    low_soiling_threshold_pct: float | None = Field(default=None, ge=1, le=50)
    min_clean_interval_days: int | None = Field(default=None, ge=1, le=365)
    wind_limit_ms: float | None = Field(default=None, ge=1, le=60)
    rain_limit_mm: float | None = Field(default=None, ge=0, le=50)


class SoilingEstimateRequest(BaseModel):
    """污损评估：基于模型估算，不是传感器实测。"""

    pm10: float | None = Field(default=None, ge=0, le=2000, description="PM10 μg/m³，缺省用配置基准")
    pm2_5: float | None = Field(default=None, ge=0, le=1000, description="PM2.5 μg/m³")
    dust: float | None = Field(default=None, ge=0, le=5000, description="沙尘浓度 μg/m³")
    days_since_clean: int | None = Field(default=None, ge=0, le=365, description="距上次清洗天数")
    expected_rain_mm: float | None = Field(default=None, ge=0, le=200, description="预计降雨 mm（用于自然清洁标注）")


class EconomicsRequest(BaseModel):
    """经济性分析：与主决策使用同一套 pv_model 公式。"""

    capacity_mw: float | None = Field(default=None, ge=0.5, le=5000)
    days_since_clean: int | None = Field(default=None, ge=0, le=365)
    price_per_kwh: float | None = Field(default=None, ge=0.05, le=2.0)
    cleaning_cost: float | None = Field(default=None, ge=0, le=10_000_000)
    scenario: Literal["demo", "live"] = "demo"
    include_sensitivity: bool = False


# ---------------------------------------------------------------------------
# 基础接口
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": llm.mode(),
        "version": APP_VERSION,
        "mcp_enabled": os.getenv("MCP_ENABLED", "1") == "1",
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


@app.get("/api/config")
def config():
    return load_config({})


@app.get("/api/site/config")
def site_config():
    return load_config({})


@app.put("/api/site/config")
def update_site_config(payload: SiteConfigUpdate):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise ValueError("没有可更新的字段")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    site_map = {
        "name": "name", "city": "city", "lat": "lat", "lng": "lng",
        "capacity_mw": "capacity_mw", "days_since_clean": "days_since_clean",
    }
    econ_map = {
        "price_per_kwh": "price_per_kwh", "cleaning_cost": "cleaning_cost",
        "labor_cost": "labor_cost", "water_cost": "water_cost",
        "equipment_cost": "equipment_cost", "efficiency": "efficiency",
        "recovery_efficiency": "recovery_efficiency", "horizon_days": "horizon_days",
        "downtime_hours": "downtime_hours",
    }
    soiling_map = {
        "base_rate_per_day": "base_rate_per_day", "pm10_ref": "pm10_ref",
        "pm10_factor": "pm10_factor", "max_loss": "max_loss",
        "low_soiling_threshold_pct": "low_soiling_threshold_pct",
        "min_clean_interval_days": "min_clean_interval_days",
    }
    safety_map = {"wind_limit_ms": "wind_limit_ms", "rain_limit_mm": "rain_limit_mm"}
    for key, target in site_map.items():
        if key in updates:
            config["site"][target] = updates.pop(key)
    for key, target in econ_map.items():
        if key in updates:
            config["economics"][target] = updates.pop(key)
    for key, target in soiling_map.items():
        if key in updates:
            config["soiling"][target] = updates.pop(key)
    for key, target in safety_map.items():
        if key in updates:
            config["safety"][target] = updates.pop(key)
    if updates:
        raise ValueError(f"不支持的更新字段：{', '.join(sorted(updates))}")
    validate_config(config)
    config.setdefault("scenario", "demo")
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("站点配置已更新：%s", ", ".join(payload.model_dump(exclude_none=True).keys()))
    return config


@app.get("/api/data-sources/health")
def data_sources_health():
    return {"sources": get_health()}


# ---------------------------------------------------------------------------
# 数据源查询接口（源失败返回 200 + ok=false + error_message，不伪装成功）
# ---------------------------------------------------------------------------

@app.get("/api/weather")
async def weather_query(
    lat: float = Query(default=44.01, ge=-90, le=90, description="纬度"),
    lng: float = Query(default=87.31, ge=-180, le=180, description="经度"),
):
    result = await get_forecast(lat, lng)
    days = result.get("days") or []
    record = result.get("record") or {}
    return {
        "ok": bool(days),
        "record": record,
        "days": days,
        "error_message": record.get("error_message"),
    }


@app.get("/api/air")
async def air_query(
    lat: float = Query(default=44.01, ge=-90, le=90, description="纬度"),
    lng: float = Query(default=87.31, ge=-180, le=180, description="经度"),
):
    result = await get_air(lat, lng)
    air = result.get("air") or {}
    record = result.get("record") or {}
    return {
        "ok": bool(air),
        "record": record,
        "air": air,
        "error_message": record.get("error_message"),
    }


@app.get("/api/pv/theoretical")
async def pv_theoretical_query(
    lat: float = Query(default=44.01, ge=-90, le=90, description="纬度"),
    lng: float = Query(default=87.31, ge=-180, le=180, description="经度"),
    loss_pct: float = Query(default=10, ge=0, le=30, description="PVGIS 系统损失 %"),
):
    result = await get_pvgis(lat, lng, loss_pct)
    pvgis = result.get("pvgis")
    record = result.get("record") or {}
    return {
        "ok": bool(pvgis),
        "record": record,
        "pvgis": pvgis,
        "error_message": record.get("error_message"),
    }


# ---------------------------------------------------------------------------
# 污损评估与经济性分析
# ---------------------------------------------------------------------------

@app.post("/api/soiling/estimate")
def soiling_estimate(payload: SoilingEstimateRequest):
    config = load_config({})
    values = payload.model_dump(exclude_none=True)
    days = int(values.pop("days_since_clean", config["site"]["days_since_clean"]))
    rain = values.pop("expected_rain_mm", 0.0)
    config["site"]["days_since_clean"] = days
    context = {
        "forecast": {
            "days": [{"date": "评估日", "irradiance": 5.8, "rain": float(rain), "wind": 9.0, "cloud": 0}],
            "source": "user_input",
            "quality": "user_input",
        },
        "air": {
            "pm10": values.get("pm10", config["soiling"]["pm10_ref"]),
            "pm2_5": values.get("pm2_5"),
            "dust": values.get("dust"),
            "source": "user_input",
            "quality": "user_input",
        },
        "theoretical": None,
        "quality": "user_input",
        "data_source_records": [],
    }
    soiling = estimate_soiling(config, context)
    return {
        "result_kind": "model_estimate",
        "note": "污损损失为模型估算，非传感器实测；线性累积假设，未建模沙尘事件突发性。",
        "soiling": soiling,
    }


@app.post("/api/economics/analyze")
async def economics_analyze(payload: EconomicsRequest):
    overrides = payload.model_dump(exclude_none=True)
    include_sensitivity = bool(overrides.pop("include_sensitivity", False))
    config = load_config(overrides)
    if config.get("scenario") == "live":
        context = await fetch_context(
            config["site"]["lat"],
            config["site"]["lng"],
            loss_pct=config["economics"].get("pvgis_loss_pct", 10.0),
        )
    else:
        context = demo_context()
    metrics = compute_metrics(config, context, include_sensitivity=include_sensitivity)
    return {
        "result_kind": "model_estimate",
        "note": "收益为估算模型，执行前请结合现场检测复核。",
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# 模拟实验室
# ---------------------------------------------------------------------------

@app.get("/api/simulation/defaults")
def simulation_defaults():
    return simulation_defaults_payload()


@app.post("/api/simulation/calculate")
def simulation_calculate(payload: SimulationRequest):
    return calculate_simulation(payload.model_dump())


# ---------------------------------------------------------------------------
# 多 Agent 主决策与 Function Calling 问答（NDJSON 流式输出）
# ---------------------------------------------------------------------------

@app.post("/api/decide/stream")
async def decide_stream(payload: DecisionRequest):
    overrides = payload.model_dump()

    async def gen():
        async for event in stream_decision(overrides):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/agent/stream")
async def agent_stream(payload: AgentRequest):
    overrides = payload.model_dump()
    question = overrides.pop("question")

    async def gen():
        async for event in stream_agent(question, overrides):
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8001"))
    print(f"疆光 · 清洗决策 Agent 已启动：http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
