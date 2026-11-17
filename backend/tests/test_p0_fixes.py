"""P0 Bug 修复验证测试。

P0-1: MCP 客户端超时后请求/响应不错位（校验 id 匹配，丢弃残留响应）
P0-2: calc_economics 的 mode 与 config.scenario 解耦时降级防线不被绕过
"""

import json
import sys
import textwrap
from pathlib import Path

import pytest

from mcp_client import MCPClient
from agent_tools import dispatch


# ---------- P0-1: MCP 响应 id 错位修复 ----------

# 构造一个 server：收到请求时先吐一行 id=999 的残留响应，再吐正确响应。
# 修复前：client.request 拿到 id=999 的错位响应。
# 修复后：client.request 丢弃 id=999，拿到匹配自己 id 的响应。
RESIDUE_SERVER = textwrap.dedent(
    """
    import json, sys
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        req_id = req.get("id")
        if req_id is None:
            continue
        # 先吐一行残留响应（模拟之前超时请求的迟到响应）
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": 999, "result": {"stale": True}}) + "\\n")
        sys.stdout.flush()
        # 再吐正确响应
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": {"ok": True, "echo": req_id}}) + "\\n")
        sys.stdout.flush()
    """
)


def test_p0_1_client_discards_stale_response_by_id_mismatch(tmp_path):
    """P0-1: client.request 必须校验响应 id，丢弃错位残留响应。"""
    server = tmp_path / "residue_server.py"
    server.write_text(RESIDUE_SERVER, encoding="utf-8")
    client = MCPClient(timeout=5, server_path=server)
    try:
        # 第一行残留 id=999 应被丢弃，拿到 id=1 的正确响应
        result = client.request("ping", {})
        assert result == {"ok": True, "echo": 1}, f"拿到错位响应：{result}"
        # 第二次请求同样应丢弃残留，拿到 id=2
        result2 = client.request("ping", {})
        assert result2 == {"ok": True, "echo": 2}, f"拿到错位响应：{result2}"
    finally:
        client.close()


def test_p0_1_client_still_raises_on_real_timeout(tmp_path):
    """P0-1 修复不破坏超时行为：真超时仍抛 TimeoutError。"""
    slow = tmp_path / "slow_server.py"
    slow.write_text("import sys\nfor line in sys.stdin:\n    pass\n", encoding="utf-8")
    client = MCPClient(timeout=0.5, server_path=slow)
    try:
        with pytest.raises(TimeoutError, match="超时"):
            client.request("initialize", {})
    finally:
        client.close()


# ---------- P0-2: mode 与 scenario 解耦降级防线 ----------

def _fallback_context():
    """模拟 live 模式下接口失败降级的 fallback context（quality=fallback）。"""
    return {
        "forecast": {
            "source": "open-meteo-fallback",
            "quality": "fallback",
            "fetched_at": "2026-11-17T00:00:00Z",
            "days": [
                {"date": "2026-11-17", "irradiance": 5.0, "rain": 0.0, "wind": 5.0},
                {"date": "2026-11-18", "irradiance": 5.2, "rain": 0.0, "wind": 4.0},
            ],
        },
        "air": {"pm10": 120, "pm2_5": 40, "dust": 0.3, "quality": "fallback"},
        "pvgis": {"E_d": 95.0, "source": "pvgis-fallback", "quality": "fallback"},
        "quality": "fallback",
    }


def _base_config(scenario="demo"):
    """与 data/pv_config.json 同构的最小 config。"""
    return {
        "site": {"lat": 44.01, "lng": 87.31, "capacity_mw": 20, "days_since_clean": 20},
        "economics": {"price_per_kwh": 0.25, "cleaning_cost": 4000, "efficiency": 0.82,
                      "horizon_days": 14, "downtime_hours": 4, "pvgis_loss_pct": 10,
                      "pvgis_angle": 35, "recovery_efficiency": 0.95},
        "soiling": {"base_rate_per_day": 0.004, "pm10_ref": 80, "pm10_factor": 0.00035,
                    "pm25_ref": 35, "pm25_factor": 0.0, "max_loss": 0.15,
                    "low_soiling_threshold_pct": 5, "min_clean_interval_days": 14,
                    "tilt_factor": 1.0, "rain_clean_threshold_mm": 2.0, "rain_clean_effect": 0.3},
        "safety": {"wind_limit_ms": 12, "rain_limit_mm": 1.0},
        "scenario": scenario,
    }


def test_p0_2_dispatch_mode_live_with_demo_scenario_triggers_insufficient(monkeypatch):
    """P0-2: config.scenario=demo 但 LLM 传 mode=live + fallback 数据 → insufficient_data。

    修复前：防线只查 config.scenario=="live"（demo 不触发）→ 用模拟数据出 clean 决策。
    修复后：mode 同步到 config.scenario → 防线触发 → insufficient_data。
    """
    import agent_tools

    # mode=live 走 fetch_context（async），mock 为返回 fallback 数据
    async def _fake_fetch(*args, **kwargs):
        return _fallback_context()
    monkeypatch.setattr(agent_tools, "fetch_context", _fake_fetch)

    config = _base_config(scenario="demo")

    # LLM 在 demo 场景下自主传 mode=live
    result = dispatch("calc_economics", {"mode": "live"}, config)
    action = result["decision"]["action"]
    assert action == "insufficient_data", (
        f"P0-2 未修复：demo 场景传 mode=live + fallback 数据应拒绝决策，实际 action={action}"
    )


def test_p0_2_dispatch_demo_mode_still_works(monkeypatch):
    """P0-2 修复不破坏正常 demo 路径：mode=demo + demo 数据 → 正常决策。"""
    import agent_tools
    from weather import demo_context as real_demo

    monkeypatch.setattr(agent_tools, "demo_context", real_demo)

    config = _base_config(scenario="demo")

    result = dispatch("calc_economics", {"mode": "demo"}, config)
    assert result["decision"]["action"] is not None
    assert result["economics"]["net_gain"] is not None
