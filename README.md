# PV-Clean-Decision · 疆光清洗决策驾驶舱

面向新疆沙尘地区的光伏电站清洗决策智能体。基于公开气象/空气质量/PVGIS 数据源与确定性污损-经济模型，通过七个规则 Agent（LLM 可选增强）给出 **建议清洗 / 建议延后 / 暂不清洗 / 数据不足** 四种决策，全程标注数据来源、估算属性与不确定性。

> 所有污损与收益结果均为**模型估算**，不是传感器实测；demo/simulation 模式使用内置样例数据，不代表真实电站运行数据。

## 核心能力

| 模块 | 说明 |
|---|---|
| 决策驾驶舱 | 电站信息、环境指标、污损风险、经济测算、决策证据与风险、数据质量面板一屏展示 |
| 七 Agent 主决策 | Weather / Soiling / PV Performance / Economic / Safety / Critic / Decision 真实执行，输出结论、证据、数据源、假设与不确定性 |
| MCP 工具层 | JSON-RPC 2024-11-05 真实协议，`get_site_data` / `search_knowledge` / `calc_economics` 三个工具，参数校验 + 失败降级 |
| Function Calling 问答 | 配置 LLM 后模型自主调用工具回答自然语言问题 |
| 模拟实验室 | 17 个参数实时重算、三策略对照（固定周期/污损阈值/天气经济联合）、示例场景、影响曲线 |
| 数据质量面板 | 每条数据的来源、获取时间、覆盖时间、单位、类型、缓存、模拟、缺失与错误原因 |

## 快速开始

### 环境要求

- Python 3.10+（推荐 3.12）
- 无需数据库、无需前端构建、数据源全部免 API Key

### 启动

```bash
# 方式一：一键启动（Linux/macOS）
bash run.sh
# 服务运行在 http://127.0.0.1:8001

# 方式二：手动启动
python3 -m pip install -r requirements.txt
cd backend
python3 main.py
```

打开浏览器访问 `http://127.0.0.1:8001`。

### 环境变量

复制 `.env.example` 为 `.env` 并按需修改：

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_BASE_URL` | ModelArts MaaS | OpenAI 兼容接口地址；不配置时主决策走纯规则引擎 |
| `LLM_API_KEY` | 空 | LLM 密钥；为空时 Function Calling 问答不可用（主决策不受影响） |
| `LLM_MODEL` | deepseek-v4.1-flash-1017 | 模型名 |
| `DS_TIMEOUT` | 10 | 数据源单次请求超时（秒） |
| `DS_RETRIES` | 2 | 数据源失败重试次数 |
| `DS_CACHE_TTL` | 21600 | PVGIS 缓存有效期（秒） |
| `MCP_ENABLED` | 1 | 是否启用 MCP 子进程；设 0 走进程内直连 |
| `PORT` | 8001 | 后端监听端口 |
| `LOG_LEVEL` | INFO | 日志级别 |

## API 概览

完整文档见 [docs/API.md](docs/API.md)。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（模式、版本、MCP 状态） |
| GET | `/api/config` | 读取电站配置 |
| GET/PUT | `/api/site/config` | 电站参数管理（白名单字段写入 pv_config.json） |
| GET | `/api/data-sources/health` | 数据源健康状态 |
| GET | `/api/weather?lat=&lng=` | 天气预报查询（Open-Meteo） |
| GET | `/api/air?lat=&lng=` | 空气质量查询（Open-Meteo Air） |
| GET | `/api/pv/theoretical?lat=&lng=&loss_pct=` | PVGIS 理论发电量查询 |
| POST | `/api/soiling/estimate` | 污损评估（模型估算） |
| POST | `/api/economics/analyze` | 经济性分析（与主决策同一套公式） |
| POST | `/api/decide/stream` | 多 Agent 主决策（NDJSON 流式） |
| POST | `/api/agent/stream` | Function Calling 问答（NDJSON 流式） |
| GET | `/api/simulation/defaults` | 模拟实验室默认参数与示例场景 |
| POST | `/api/simulation/calculate` | 模拟实验室实时计算 |

## 错误处理规则

| 场景 | HTTP 状态 | 行为 |
|---|---|---|
| 参数越界/类型错误 | 422 | Pydantic 校验失败，返回字段级错误 |
| 业务参数非法（如站点配置含负值） | 400 | `{"detail": "...", "code": "invalid_params"}` |
| 数据源失败（天气/空气/PVGIS） | 200 | `{"ok": false, "error_message": "..."}`，不伪装成功 |
| MCP 不可用 | 流内事件 | `mcp_error` 事件，自动回退进程内直连 |
| LLM 不可用 | 正常 | 主决策走纯规则引擎；问答返回 `agent_error` |
| 后端内部错误 | 500 | `{"detail": "...", "code": "internal_error"}`，日志记录完整堆栈 |

## 测试

```bash
python3 -m pytest backend/tests -q
```

当前基线：**147 项全绿**（含模拟实验室 30 项）。

## 文档索引

- [docs/API.md](docs/API.md) — 接口文档（参数、响应、错误码）
- [docs/AGENT_ARCHITECTURE.md](docs/AGENT_ARCHITECTURE.md) — 七 Agent 架构
- [docs/SIMULATION_LAB.md](docs/SIMULATION_LAB.md) — 模拟实验室
- [docs/ALGORITHM_EXPLANATION.md](docs/ALGORITHM_EXPLANATION.md) — 决策模型与公式
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) — 数据源接入
- [readme/README.md](readme/README.md) — 详细说明（含答辩口径）

## 技术栈

- 后端：Python 3.10+ / FastAPI / Pydantic / httpx / uvicorn
- 前端：原生 HTML/CSS/JS 单文件，零构建零依赖
- 协议：MCP JSON-RPC 2024-11-05（stdio 子进程）
- 数据源：Open-Meteo Forecast / Open-Meteo Air Quality / PVGIS（欧盟 JRC）

## 许可

仅用于比赛与学习演示，不得作为工程决策依据。
