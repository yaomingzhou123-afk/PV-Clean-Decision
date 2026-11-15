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