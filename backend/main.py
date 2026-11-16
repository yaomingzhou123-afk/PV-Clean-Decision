import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from env_loader import load_env

load_env()

import json
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import llm
from agent_loop import stream_agent
from data_sources.health import get_health
from orchestrator import load_config, stream_decision
from simulation_lab import calculate as calculate_simulation
from simulation_lab import defaults_payload as simulation_defaults_payload

ROOT = BASE_DIR.parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="光伏电站沙尘清洗决策 Agent")


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


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    return {"ok": True, "mode": llm.mode()}


@app.get("/api/config")
def config():
    return load_config({})


@app.get("/api/data-sources/health")
def data_sources_health():
    return {"sources": get_health()}


@app.get("/api/simulation/defaults")
def simulation_defaults():
    return simulation_defaults_payload()


@app.post("/api/simulation/calculate")
def simulation_calculate(payload: SimulationRequest):
    return calculate_simulation(payload.model_dump())


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