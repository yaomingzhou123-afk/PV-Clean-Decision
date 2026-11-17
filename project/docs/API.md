# API 文档

基础地址：`http://127.0.0.1:8001`（由 `PORT` 环境变量控制）。交互式文档：`/docs`（FastAPI 自动生成，与本文档一致）。

统一约定：

- 请求/响应均为 JSON（`Content-Type: application/json`）。
- 流式接口返回 NDJSON（`application/x-ndjson`），每行一个事件对象，含 `type` 与 `ts` 字段。
- 错误响应统一格式：`{"detail": "...", "code": "..."}`。
  - 422：Pydantic 校验失败，`detail` 为字段级错误数组。
  - 400：业务参数非法，`code: "invalid_params"`。
  - 500：内部错误，`code: "internal_error"`，完整堆栈在后端日志。
- 数据源查询接口（天气/空气/PVGIS）在源失败时返回 **200** + `{"ok": false, "error_message": "..."}`，不伪装成功。

---

## 基础接口

### GET /api/health

健康检查。

```json
{
  "ok": true,
  "mode": "rule",
  "version": "3.0.7",
  "mcp_enabled": true,
  "time": "2026-11-16T20:00:00+0800"
}
```

`mode`：`"llm"`（已配置 LLM）或 `"rule"`（纯规则引擎）。

### GET /api/config

读取电站完整配置（等价于 `GET /api/site/config`）。

### GET /api/site/config

同 `/api/config`，语义化别名。

### PUT /api/site/config

更新电站参数（白名单字段，写入 `backend/data/pv_config.json`）。只传需要更新的字段。

请求示例：

```json
{
  "name": "准东光伏电站",
  "lat": 44.01,
  "lng": 87.31,
  "capacity_mw": 20,
  "days_since_clean": 20,
  "price_per_kwh": 0.25,
  "cleaning_cost": 4000,
  "wind_limit_ms": 12,
  "rain_limit_mm": 1.0
}
```

可更新字段：`name, city, lat, lng, capacity_mw, days_since_clean, price_per_kwh, cleaning_cost, labor_cost, water_cost, equipment_cost, efficiency, recovery_efficiency, horizon_days, downtime_hours, base_rate_per_day, pm10_ref, pm10_factor, max_loss, low_soiling_threshold_pct, min_clean_interval_days, wind_limit_ms, rain_limit_mm`。

响应：更新后的完整配置。空请求返回 400。

### GET /api/data-sources/health

返回数据源健康状态列表（源名、状态、延迟、错误、类型、缓存、检查时间）。

---

## 数据源查询

### GET /api/weather?lat=&lng=

Open-Meteo 天气预报（3 天）。参数：`lat`（-90~90，默认 44.01）、`lng`（-180~180，默认 87.31）。

```json
{
  "ok": true,
  "record": { "source": "open-meteo", "data_kind": "forecast", "fetched_at": "...", "valid_time": "未来 3 天", "unit": {"irradiance": "kWh/m²", ...}, "status": "ok", "is_simulated": false, ... },
  "days": [{ "date": "2026-11-17", "irradiance": 5.8, "rain": 0.0, "wind": 9.0, "cloud": 10, ... }],
  "error_message": null
}
```

### GET /api/air?lat=&lng=

Open-Meteo 空气质量（PM10/PM2.5/沙尘）。参数同上。

```json
{
  "ok": true,
  "record": { "source": "open-meteo-air", ... },
  "air": { "pm10": 135.0, "pm2_5": 24.0, "dust": 120.0, ... },
  "error_message": null
}
```

### GET /api/pv/theoretical?lat=&lng=&loss_pct=

PVGIS 历史气候理论发电量。参数：`lat`、`lng`、`loss_pct`（0~30，默认 10）。

```json
{
  "ok": true,
  "record": { "source": "pvgis", "data_kind": "historical", ... },
  "pvgis": { "E_d": 3.79, "month": 11, "radiation_db": "PVGIS-ERA5", "year_min": 2005, "year_max": 2023 },
  "error_message": null
}
```

---

## 污损评估与经济性分析

### POST /api/soiling/estimate

污损评估（模型估算，非传感器实测）。全部字段可选，缺省用配置默认值。

请求示例：

```json
{
  "pm10": 135.0,
  "pm2_5": 24.0,
  "dust": 120.0,
  "days_since_clean": 20,
  "expected_rain_mm": 0.0
}
```

响应：`{"result_kind": "model_estimate", "note": "...", "soiling": {...}}`。`soiling` 含 `loss_pct`、`daily_rate_pct`、`drivers`、`limitations`、`method`（`model_estimate`）等。

### POST /api/economics/analyze

经济性分析，与主决策使用同一套 `pv_model` 公式。

请求示例：

```json
{
  "capacity_mw": 20,
  "days_since_clean": 20,
  "price_per_kwh": 0.25,
  "cleaning_cost": 4000,
  "scenario": "demo",
  "include_sensitivity": false
}
```

响应：`{"result_kind": "model_estimate", "note": "...", "metrics": {...}}`。`metrics` 与主决策的 `final.metrics` 结构一致（含 `decision`、`economics`、`soiling`、`weather`、`data_quality`）。

---

## 多 Agent 主决策（流式）

### POST /api/decide/stream

请求：

```json
{
  "capacity_mw": 20,
  "days_since_clean": 20,
  "price_per_kwh": 0.25,
  "cleaning_cost": 4000,
  "scenario": "demo"
}
```

响应为 NDJSON 流，事件按序输出：

| 事件 type | 说明 |
|---|---|
| `session_start` | 会话开始（站点、经济配置、模式） |
| `mcp_ready` / `mcp_error` | MCP 握手结果（失败自动回退直连） |
| `mcp_tool_call` | MCP 工具调用（工具名、耗时） |
| `data_loaded` | 数据加载完成（天气、空气、数据质量） |
| `decision_snapshot` | 规则引擎决策快照（完整 metrics） |
| `round_start` | 协商轮次开始 |
| `agent_result` | 七 Agent 结构化输出（名称/职责/状态/结论/证据/数据源/假设/不确定性/置信度/否决类型） |
| `agent_speak` | 兼容事件（第一轮与 agent_result 内容相同，前端择一渲染） |
| `critic_issues` | Critic 审查发现的问题列表（severity/agent/issue） |
| `agent_decision` | Decision Agent 最终仲裁（final_action/veto_applied/llm_enhanced/decision_trace） |
| `agent_input` | 第二轮旧协商 Agent 的输入快照 |
| `final` | 最终决策（含完整 metrics、forced、summary） |
| `pipeline_error` | 管线执行失败（数据获取或计算异常） |

`agent_result` 事件结构：

```json
{
  "type": "agent_result",
  "agent": "safety",
  "role": "Operation & Safety Agent",
  "goal": "检查用户配置的安全阈值、风速、降雨与数据质量，必要时否决",
  "result": {
    "agent_name": "safety",
    "status": "ok",
    "conclusion": "...",
    "evidence": [{ "metric": "wind_max", "value": 9.0, "threshold": 12, "unit": "m/s", "verdict": "below" }],
    "data_sources": [{ "source": "demo-builtin", "data_kind": "simulation", "is_simulated": true, "status": "ok" }],
    "assumptions": ["..."],
    "uncertainties": ["..."],
    "recommendation": "clear",
    "confidence_type": "heuristic",
    "confidence": 0.95,
    "veto_type": null,
    "inputs_read": { "...": "..." }
  }
}
```

`confidence_type` 固定为 `"heuristic"`（启发式评分，非概率）或 `"none"`。

---

## Function Calling 问答（流式）

### POST /api/agent/stream

请求：

```json
{
  "question": "现在适合清洗吗？能赚多少？",
  "scenario": "demo",
  "capacity_mw": 20,
  "days_since_clean": 20,
  "price_per_kwh": 0.25,
  "cleaning_cost": 4000
}
```

事件序列：`agent_start` → `agent_mcp_ready`/`agent_mcp_error` → (`agent_decision` → `agent_tool_call` → `agent_tool_result`)* → `agent_answer` / `agent_error`。

未配置 LLM 时直接返回 `agent_error`（message 说明原因），主决策链路不受影响。

---

## 模拟实验室

### GET /api/simulation/defaults

返回 17 个参数的规格（单位/范围/默认值/说明/依据）、3 个示例场景、项目阈值、假设与局限。所有默认值标注为示例假设或项目配置值，不是行业标准。

### POST /api/simulation/calculate

请求（全部字段可选，缺省用默认值）：

```json
{
  "pm10": 80, "pm2_5": 24, "dry_days": 20,
  "soiling_override_pct": null,
  "capacity_mw": 20, "tilt_angle_deg": 35,
  "price_per_kwh": 0.25,
  "labor_cost": 2000, "water_cost": 1000, "equipment_cost": 1000,
  "expected_rain_mm": 0, "wind_speed_ms": 9,
  "recovery_efficiency": 0.95,
  "avg_irradiance_kwh_m2_day": 5.8,
  "horizon_days": 30, "fixed_cycle_days": 30, "soiling_threshold_pct": 5,
  "scenario_name": "自定义模拟场景（模拟）"
}
```

响应：`summary`（污损风险/发电损失/成本/收益/净收益/回本/天气/决策）、`strategies`（三策略对照）、`impact`（9 组单因素影响曲线）、`warnings`、`assumptions`、`limitations`、`formulas`。所有结果带 `result_kind: "simulation"` 与免责声明。

---

## MCP 工具

MCP Server（`backend/mcp_server.py`）通过 stdio 子进程提供 JSON-RPC 2024-11-05 协议，可独立调用：

```bash
cd backend && python3 mcp_client.py   # 冒烟测试
```

| 工具 | 参数 | 校验 | 失败行为 |
|---|---|---|---|
| `get_site_data` | `lat`（-90~90）、`lng`（-180~180）、`loss_pct`（0~30）、`mode`（live/demo） | 越界返回 `-32602` | 源失败降级样例并标注 `is_simulated` |
| `search_knowledge` | `query`（非空字符串）、`applies_to`（可选字符串）、`top_k`（1~10） | 越界返回 `-32602` | — |
| `calc_economics` | `config`/`context` 可选（缺省用服务端配置 + 按 mode 拉取数据） | 非对象返回 `-32602` | 计算异常返回 `-32603` |

客户端（`backend/mcp_client.py`）带 30 秒读超时与幂等关闭；握手失败自动回退进程内直连，不中断主决策。

---

## 错误码汇总

| HTTP | code | 场景 |
|---|---|---|
| 200 | — | 正常（数据源失败时 `ok: false` + `error_message`） |
| 400 | `invalid_params` | 业务参数非法（ValueError） |
| 422 | `validation_error` | Pydantic 校验失败（字段级错误数组） |
| 500 | `internal_error` | 未处理异常（日志含完整堆栈） |

MCP JSON-RPC 错误码：`-32601`（未知工具）、`-32602`（参数无效）、`-32603`（执行异常）、`-32700`（JSON 解析错误）。
