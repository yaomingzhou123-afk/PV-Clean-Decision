# 疆光 · 光伏电站沙尘清洗决策 Agent

2026 华为开发者大赛·智能体创新赛（昌吉学院站）参赛作品。

## 一句话说明

输入光伏电站装机与运行状态，拉取公开气象与沙尘数据，由多个目标互相冲突的 Agent 协商，输出"今天该不该洗、什么时候洗、能多赚多少钱"的可执行决策。

## 项目背景

新疆光伏装机规模大、沙尘频发。板面污损会直接压低发电量（模型上限 15%），但清洗有成本（单次约 4000 元/20MW）、有停机损失、还受天气窗口限制。什么时候洗是一个真实的、可算账的决策问题，目前主要依赖人工经验，缺乏可解释、可追溯的量化工具。

## 核心功能

1. **决策驾驶舱**：一屏展示七 Agent 逐个执行、KPI 带、决策结论、证据表、数据质量标注
2. **模拟实验室**：17 个参数实时重算污损/收益/决策，支持 PM10、电价、清洗成本等单因素敏感性分析
3. **Agent 问答**：自然语言提问 → LLM 自主调用工具链（get_site_data / search_knowledge / calc_economics）→ 带知识库引用的回答
4. **三种数据模式**：演示样例（断网可用）/ 实时公开数据 / 模拟实验室
5. **诚实标注**：模拟数据标 `is_simulated=true`，模型估算标 `model_estimate`，数据不足拒绝决策而非编造

## 与常见方案的差异

1. 不做问答机器人，输出的是带收益明细的执行决策
2. 七个 Agent 目标互相冲突，Safety 可一票否决、Critic 可驳回，协商过程对用户可见
3. 全部使用公开免费数据，不需要购买任何 API
4. 无模型 Key 也能完整运行；演示样例可在断网环境复现

## 目录结构

交付包按官方五件套组织：

```
PV-Clean-Decision/
├─ ppt/                          答辩 PPT 与辅助材料
│  ├─ PV-Clean-Decision-答辩PPT.pptx
│  ├─ PV-Clean-Decision-答辩PPT.pdf
│  ├─ 逐页演讲稿.md
│  ├─ 评委问答参考.md
│  ├─ build_ppt.js               PPT 构建脚本
│  └─ screenshots/               PPT 截图素材（6 张）
├─ project/                      完整源代码
│  ├─ backend/
│  │  ├─ main.py                 FastAPI 入口与流式接口
│  │  ├─ orchestrator.py         协商轮次编排
│  │  ├─ agent_team.py           七个 Agent 协作
│  │  ├─ agents.py               Agent 个体逻辑
│  │  ├─ agent_loop.py           LLM Function Calling 循环
│  │  ├─ agent_tools.py          工具调度（进程内直连路径）
│  │  ├─ pv_model.py             发电量、污损、收益、决策模型
│  │  ├─ weather.py              公开气象与空气质量数据接入
│  │  ├─ llm.py                  可选 LLM 适配层
│  │  ├─ mcp_server.py           MCP Server（JSON-RPC 2.0 over stdio）
│  │  ├─ mcp_client.py           MCP Client（子进程通信）
│  │  ├─ simulation_lab.py       模拟实验室
│  │  ├─ kb/
│  │  │  ├─ knowledge.jsonl      RAG 知识库（37 条 / 6 类）
│  │  │  └─ retriever.py         BM25 检索（零依赖）
│  │  ├─ data/pv_config.json     电站参数与模型参数
│  │  ├─ utils/units.py          单位换算
│  │  └─ tests/                  210 项测试（18 个文件）
│  ├─ frontend/index.html        单页前端（零构建，1032 行）
│  ├─ docs/                      6 份技术文档
│  ├─ .github/workflows/ci.yml   GitHub Actions CI（Python 3.10-3.12 矩阵）
│  ├─ .env.example               环境变量模板
│  ├─ requirements.txt           Python 依赖
│  ├─ run.sh                     一键启动（macOS / Linux）
│  ├─ run.bat                    一键启动（Windows，自动建 venv）
│  ├─ start.bat                  Windows 启动（含 .env 引导）
│  └─ .vscode/launch.json        VS Code F5 调试配置
├─ video/
│  └─ PV-Clean-Decision-功能演示视频.mp4   2 分 11 秒 / H.264 / 4.4MB
├─ codearts_proof/               码道使用证明（8 份开发记录 + 截图要求）
│  ├─ 00_总览与规范依据.md
│  ├─ 01_需求分析与选题记录.md
│  ├─ 02_架构设计记录.md
│  ├─ 03_编码与迭代记录.md
│  ├─ 04_调试与Bug修复记录.md
│  ├─ 05_测试与验收记录.md
│  ├─ 06_数据接入实测记录.md
│  ├─ 07_版本与部署记录.md
│  └─ screenshots/               真实操作截图（见 NEED.md 说明）
└─ readme/
   └─ README.md                  本文件
```

## 系统架构

四层架构：数据源 → MCP 工具层 → 七 Agent 决策 → 前端驾驶舱

```
前端(零构建 SPA) ──POST NDJSON 流──▶ FastAPI
                                     │
                        orchestrator.stream_decision()
                          1. 参数校验(pydantic + validate_config)
                          2. 数据层 weather.fetch_context()
                          3. compute_metrics() 算污损/收益/决策
                          4. run_team() 七 Agent 协商
                          5. 敏感性分析 + 事件流输出
```

## 七个 Agent 职责

| Agent | 职责 | 可否决情形 |
|---|---|---|
| Weather 气象分析官 | 判断作业窗口（降水/风速/辐照） | 降水或风速超限 → defer |
| Soiling 污损评估官 | 量化发电损失（PM10/PM2.5 驱动） | 损失率低于 5% → 不值得洗 |
| PV Performance 发电分析官 | 理论发电量与可恢复电量 | 无否决权，提供数据 |
| Economic 收益核算官 | 净收益/回本周期/停机损失 | 净收益为负 → hold |
| Safety 安全否决官 | 一票否决（数据质量/天气/间隔） | 任一条件触发 → 否决 |
| Critic 审查主席 | 驳回不合理结论（四类审查） | 计算错误/逻辑矛盾 → 驳回 |
| Decision 最终仲裁官 | 汇总输出最终决策 | 遵守保守序，不推翻 Safety |

## Agent 协作机制

1. 七个 Agent 顺序执行（Weather → Soiling → PV → Economic → Safety → Critic → Decision），非并行各说各话
2. **Safety 三条件否决**：数据质量差 / 天气不满足 / 间隔不足，优先级最高，Decision 不得推翻
3. **Critic 四类审查**：计算错误 / 逻辑矛盾 / 数据缺失 / 阈值异常，可驳回并触发第二轮
4. **Decision 保守序**：insufficient_data > weather_block > interval_block > economics，宁可保守不洗
5. **第二轮收敛**：Critic 驳回后，仲裁官可提"分区清洗"折中方案，第二轮重新评估
6. 每个 Agent 输出含 `confidence`（确定性推导 0.6-0.99，无随机）、`evidence`（结构化依据）、`kb_refs`（知识库引用）

## MCP 调用链路

- **协议**：JSON-RPC 2.0 over stdio（MCP 2024-11-05 规范）
- **Server**：`project/backend/mcp_server.py`，暴露 3 个工具
  - `get_site_data`：获取气象/沙尘/PVGIS 理论发电量
  - `search_knowledge`：RAG 知识库检索
  - `calc_economics`：收益计算与决策结论
- **Client**：`project/backend/mcp_client.py`，子进程启动 Server，完成握手→列举工具→调用工具
- **主链路**：数据接入与收益计算均经 `tools/call` 真实调用，事件流记录工具名与耗时
- **降级**：MCP 启动失败时自动回退进程内直连（`agent_tools.dispatch`），界面标注"MCP 不可用，已回退直连"
- **关闭**：环境变量 `MCP_ENABLED=0`
- **P0-1 修复**：Client 校验响应 id 匹配，超时后丢弃残留响应，避免永久错位

## RAG 知识库

- **位置**：`project/backend/kb/knowledge.jsonl`，37 条，覆盖 6 类：安全作业、污损机理、清洗工艺、经济测算、数据口径、决策原则
- **检索**：`project/backend/kb/retriever.py` 纯 Python BM25（中文二元组切分），零依赖、无需向量库
- **引用**：每个 Agent 发言自动附带 `kb_refs`（条款 id、标题、摘要、来源、是否核实），前端以 [KB] 标签展示
- **核实状态**：`verified=true` 表示来源真实存在；`false` 表示团队整理或经验值，界面标注"待核实"
- **主要来源**：IEA PVPS Task 13 公开报告、PVGIS 官方文档、Open-Meteo 官方文档、团队作业规程

## 数据来源及限制

| 数据 | 接口 | 说明 |
|---|---|---|
| 辐照、降水、云量、风速 | Open-Meteo Forecast | 免费、无需 Key |
| PM10、PM2.5、沙尘 | Open-Meteo Air Quality | 免费、无需 Key |
| 理论发电量 | PVGIS（欧盟 JRC） | 免费、无需 Key |
| 历史辐照校验（可选） | NASA POWER | 免费、无需 Key |

接口异常时自动重试并降级为内置样例，页面标注 `is_simulated=true`。

**已知限制**：
- 污损模型为简化估算，未接入实测 IV 曲线
- 辐照为公开气象再分析/预报值，与站点实测存在偏差
- 未接入电力交易价格曲线，电价按固定值估算
- 清洗成本按元/次配置，不同清洗方式差异较大

## 环境依赖

- Python 3.10+
- 依赖：fastapi、uvicorn、httpx、pytest（全部 MIT 许可证）
- 无需 Docker、无需 Node.js、无需数据库
- 可选：LLM API Key（华为云 MaaS 或任何 OpenAI 协议端点），未配置时自动降级为规则引擎

## 安装方法

### 方式一：Windows 双击（推荐）

1. 解压交付包，进入 `project/` 目录
2. 双击 `run.bat`，首次自动创建虚拟环境并安装依赖
3. 浏览器打开 `http://127.0.0.1:8001`

### 方式二：VS Code F5

1. 用 VS Code 打开 `project/` 文件夹
2. 按 `F5`，选择「启动 光伏清洗决策 Agent」
3. 浏览器打开 `http://127.0.0.1:8001`

### 方式三：命令行（macOS / Linux / Windows 通用）

```bash
cd project
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Windows (CMD)
.venv\Scripts\activate.bat
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cd backend
python main.py            # 或：python -m uvicorn main:app --port 8001
```

不需要 Docker。只要 Python 3.10+。

## Windows 启动

- **run.bat**：自动建 `.venv` + 装依赖 + 启动，适合首次使用
- **start.bat**：含 `.env` 引导（首次自动从 `.env.example` 复制并打开记事本填 Key），适合配置 LLM
- 依赖装不上时加国内镜像：`-i https://pypi.tuna.tsinghua.edu.cn/simple`
- PowerShell 禁止激活脚本：改用 CMD 的 `activate.bat`，或 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## Linux 部署

```bash
cd project
python3 -m pip install -r requirements.txt
cd backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8001
```

或直接 `bash run.sh`（自动装依赖 + 启动）。

## 测试方法

```bash
cd project
python3 -m pip install -r requirements.txt
cd backend
python3 -m pytest tests -q
```

预期结果：**210 passed**（含 206 项原测试 + 4 项 P0 修复验证测试），耗时约 30 秒。

测试覆盖：
- 决策模型/经济/污损公式与边界（46 项）
- 七 Agent 团队执行顺序与结构校验（22 项）
- MCP 协议握手/超时/参数校验/幂等关闭（19 项）
- 数据源降级/单位换算/知识库检索
- P0 修复验证：MCP 响应 id 错位、mode/scenario 解耦防线
- 稳定性 P0 回归（3 批次）

## 开源组件说明

本项目使用的第三方开源组件如下，均通过 pip 安装，未修改任何源码：

| 组件 | 版本要求 | 许可证 | 用途 |
|---|---|---|---|
| FastAPI | >=0.115 | MIT | Web 框架，提供 REST + 流式接口 |
| uvicorn | >=0.34 | BSD-3-Clause | ASGI 服务器 |
| httpx | >=0.28 | BSD-3-Clause | HTTP 客户端，调公开数据源 |
| pytest | >=8.0 | MIT | 测试框架 |

**未使用的组件**：无 Docker、无 Node.js、无数据库、无向量库、无前端框架（原生 HTML/JS）。

**数据源 API**（均为免费公开接口，非开源组件）：
- Open-Meteo Forecast / Air Quality（免 Key，https://open-meteo.com）
- PVGIS（欧盟 JRC，免 Key，https://re.jrc.ec.europa.eu/pvest）
- NASA POWER（免 Key，https://power.larc.nasa.gov）

知识库内容来源：IEA PVPS Task 13 公开报告、PVGIS 官方文档、Open-Meteo 官方文档、团队作业规程，已在 `codearts_proof/06_数据接入实测记录.md` 记录实测过程。

## 码道在项目开发中的应用总结

本项目全程使用华为云码道（CodeArts）开发，开发过程留存于 `codearts_proof/` 目录（8 份 Markdown 记录）：

| 阶段 | 码道应用 | 记录文件 |
|---|---|---|
| 需求分析与选题 | 与码道多轮对话收敛选题，从"导购 Agent"转向"光伏沙尘清洗决策" | 01 |
| 架构设计 | 向码道提出设计约束，码道产出四层架构并经两轮评审修订 | 02 |
| 编码与迭代 | 码道生成代码，团队逐文件评审，7 个版本迭代（v2→v2.7→v3.0） | 03 |
| 调试与 Bug 修复 | 码道辅助定位 10 项 P0 级问题并修复，每条含现象/定位/修复/验证 | 04 |
| 测试与验收 | pytest 206→210 项测试演进，端到端流式接口回归 | 05 |
| 数据接入实测 | 三大公开数据源真实请求验证，失败降级路径覆盖 | 06 |
| 版本与部署 | 7 个版本记录、启动方式验证、部署记录 | 07 |

**AI 原生开发流程覆盖度**：需求分析 → 架构设计 → 代码生成 → 调试排错 → 测试验收 → 数据验证 → 部署记录，全链路留存。

**Prompt 质量**：关键 Prompt 原文要点已记录在 01/02/03 文件中，含设计约束、升级指令（9 条执行原则）、参数依据追问等。

**诚实标注**：`codearts_proof/00_总览与规范依据.md` 明确标注"全部内容来自真实开发过程，无事后编造"；`screenshots/NEED.md` 列出 4 类需补的真实截图（码道会话/代码生成/测试运行/应用运行），不伪造。

## 决策模型

```
理论日发电量 = 装机容量 × 日辐照 × 系统效率
污损损失率   = min(上限, (基础速率 + max(0, PM10 - 基准) × 系数) × 运行天数)
可恢复电量   = 理论日发电量 × 污损损失率
清洗收益     = 可恢复电量 × 电价 × 评估天数 - 清洗成本 - 停机损失
决策条件     = 未触发天气阻塞 且 距上次清洗 ≥ 最小间隔（14 天） 且 净收益 > 0
最小间隔     = 14 天：低于该值直接建议暂不清洗，仲裁不得推翻（行业实践下限）
```

参数全部在 `project/backend/data/pv_config.json` 中可调，页面已声明为估算模型。

## Function Calling（Agent 工具调用）

- 前提：配置 LLM。本项目默认对接华为云 MaaS 的 `/v2` 接口，也兼容任何 OpenAI 协议端点
- 配置（用环境变量，禁止写进代码）：
```bash
cd project
cp .env.example .env    # 然后把 LLM_API_KEY 填进去
```
`.env` 已被 `.gitignore` 排除，不会进入交付包
- 用法：页面底部「Agent 工具调用」面板输入问题，模型自主决定调用 `get_site_data` / `search_knowledge` / `calc_economics`，工具经 MCP 执行，最多 4 步
- 自检：`python backend/check_llm.py` 输出连通性、HTTP 状态、是否支持 tools
- 降级：未配置 Key 时面板提示"未配置 LLM"，主决策流程完全不受影响

## 演示视频

`video/PV-Clean-Decision-功能演示视频.mp4`（2 分 11 秒，H.264，4.4MB），内容：

| 时段 | 场景 |
|---|---|
| 0:04–0:43 | 场景A：高积灰七 Agent 决策 → 39,478 元 / 1.2 天 |
| 0:43–0:50 | 数据溯源卡 |
| 0:50–1:33 | 模拟实验室：PM10 实时重算 → 93,696 元 |
| 1:33–1:41 | 场景B：间隔未到 → 否决暂不清洗 |
| 1:41–1:48 | 场景C：断网 → 数据不足拒决策（降级防线） |
| 1:48–2:08 | Agent 问答实录：LLM 增强 + 工具链 + 知识库引用 |

## 评分点对应

| 评分维度 | 对应实现 |
|---|---|
| 创新性与价值 30 | 新疆光伏沙尘场景、可算账的清洗决策、公开数据驱动 |
| 技术实现 25 | 七 Agent 协商、MCP 真实协议、Function Calling、210 项测试、2 P0 已修 |
| 码道使用深度 25 | `codearts_proof/` 8 份记录覆盖全链路 + 截图 |
| 工程质量 12 | 零构建前端、一键启动、接口分层、参数可配置、CI 矩阵 |
| 交付规范 8 | 五件套目录结构 + 本说明文档 |
