# 疆光 · 光伏电站沙尘清洗决策 Agent

2026 华为开发者大赛·智能体创新赛（昌吉学院站）参赛作品。

## 一句话说明

输入光伏电站装机与运行状态，拉取公开气象与沙尘数据，由多个目标互相冲突的 Agent 协商，输出"今天该不该洗、什么时候洗、能多赚多少钱"的可执行决策。

## 为什么做这个

新疆光伏装机规模大、沙尘频发。板面污损会直接压低发电量，但清洗有成本、有停机损失、还受天气窗口限制。什么时候洗是一个真实的、可算账的决策问题。

## 与常见方案的差异

1. 不做问答机器人，输出的是带收益明细的执行决策。
2. 气象、污损、收益、调度四个 Agent 目标互相冲突，协商过程对用户可见。
3. 全部使用公开免费数据，不需要购买任何 API。
4. 无模型 Key 也能完整运行；演示样例可在断网环境复现。

## 目录结构

```
pv-agent/
├─ backend/
│  ├─ main.py           FastAPI 入口与流式接口（可直接运行）
│  ├─ orchestrator.py   协商轮次编排
│  ├─ agent_team.py     七个 Agent（Weather/Soiling/PV Performance/Economic/Safety/Critic/Decision）
│  ├─ agents.py         旧协商层（第二轮可视化 + 分区/延后仲裁）
│  ├─ pv_model.py       发电量、污损、收益模型
│  ├─ weather.py        公开气象与空气质量数据接入
│  ├─ llm.py            可选 LLM 适配层
│  ├─ kb/
│  │  ├─ knowledge.jsonl  RAG 知识库（37 条 / 6 类）
│  │  └─ retriever.py     BM25 检索（零依赖）
│  └─ data/pv_config.json 电站参数与模型参数
├─ frontend/index.html  单页前端（零构建）
├─ readme/README.md
├─ run.sh               一键启动（macOS / Linux）
├─ run.bat              一键启动（Windows）
└─ .vscode/launch.json  VS Code F5 调试配置
```

## Function Calling（Agent 工具调用）

- 前提：配置 LLM。本项目默认对接华为云 MaaS 的 `/v2` 接口，也兼容任何 OpenAI 协议端点
- 配置（用环境变量，禁止写进代码）：
```bash
cp .env.example .env    # 然后把 LLM_API_KEY 填进去
```
`.env` 已被打包排除，不会进入交付包；也可直接用 export 设置。
- 用法：页面底部「Agent 工具调用」面板输入问题，模型自主决定调用 `get_site_data` / `search_knowledge` / `calc_economics`，工具经 MCP 执行，最多 4 步
- 自检：`python backend/check_llm.py` 输出连通性、HTTP 状态、是否支持 tools
- 降级：未配置 Key 时面板提示"未配置 LLM"，主决策流程完全不受影响

## MCP 工具层

- 实现：`backend/mcp_server.py` 是标准 JSON-RPC 2.0 over stdio 的 MCP Server，支持 `initialize` / `tools/list` / `tools/call`
- 客户端：`backend/mcp_client.py` 以子进程方式启动 Server，完成握手、列举工具、调用工具
- 暴露工具：`get_site_data`（气象/沙尘/PVGIS）、`search_knowledge`（RAG 检索）、`calc_economics`（收益计算）
- 主链路真实经 MCP 调用：数据接入与收益计算均通过 `tools/call` 完成，事件流记录工具名与耗时
- 降级：MCP 启动失败时自动回退为进程内直连，界面显示"MCP 不可用，已回退直连"
- 可独立验证：`python backend/mcp_client.py` 输出握手信息、工具清单与一次检索结果
- 关闭方式：环境变量 `MCP_ENABLED=0`

## RAG 知识库

- 位置：`backend/kb/knowledge.jsonl`，37 条，覆盖 6 类：安全作业、污损机理、清洗工艺、经济测算、数据口径、决策原则
- 检索：`backend/kb/retriever.py` 纯 Python BM25（中文二元组切分），零依赖、无需向量库
- 引用：每个 Agent 的发言自动附带 `kb_refs`（条款 id、标题、摘要、来源、是否核实），前端以 [KB] 标签展示
- 核实状态：`verified=true` 表示来源真实存在且可访问；`false` 表示团队整理或经验值，界面标注"待核实"，不冒充权威
- 主要来源：IEA PVPS Task 13 公开报告（污损、运维、局部遮挡）、PVGIS 官方文档、Open-Meteo 官方文档、团队作业规程

## 运行

### 方式一：VS Code 一键启动（推荐）

1. 解压 `pv-agent.zip`，用 VS Code 打开 **pv-agent 文件夹**（不是单个 py 文件）
2. 按 `F5`，选择「启动 光伏清洗决策 Agent」
3. 浏览器打开 `http://127.0.0.1:8001`

### 方式二：Windows 双击

双击 `run.bat`。首次会自动创建虚拟环境并安装依赖，之后直接启动。

### 方式三：命令行（macOS / Linux / Windows 通用）

```bash
cd pv-agent
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Windows (CMD)
.venv\Scripts\activate.bat
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
cd backend
python main.py            # 或：python -m uvicorn main:app --port 8001 --reload
```

不需要 Docker。只要 Python 3.10+。

### 常见问题

- **端口被占用**：`set PORT=8002 && python main.py`（Windows）/ `PORT=8002 python main.py`（macOS/Linux）
- **依赖装不上**：加国内镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple
- **PowerShell 禁止激活脚本**：改用 CMD 的 `activate.bat`，或执行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
- **右键运行 main.py 没反应**：确认工作目录是 `backend`，或直接用 F5 配置

依赖只有 fastapi、uvicorn、httpx、pytest，Python 3.10+。

## 公开数据源

| 数据 | 接口 | 说明 |
|---|---|---|
| 辐照、降水、云量、风速 | Open-Meteo Forecast | 免费、无需 Key |
| PM10、沙尘 | Open-Meteo Air Quality | 免费、无需 Key |
| 历史辐照校验（可选） | NASA POWER | 免费、无需 Key |

接口异常时自动重试并降级为内置样例，页面会标注数据来源。

数据模式：
- 演示样例：内置夏季沙尘场景，断网可用，适合现场答辩
- 实时数据：拉取 Open-Meteo 当前预报

## 决策模型

```
理论日发电量 = 装机容量 × 日辐照 × 系统效率
污损损失率   = min(上限, (基础速率 + max(0, PM10 - 基准) × 系数) × 运行天数)
可恢复电量   = 理论日发电量 × 污损损失率
清洗收益     = 可恢复电量 × 电价 × 评估天数 - 清洗成本 - 停机损失
决策条件     = 未触发天气阻塞 且 距上次清洗 ≥ 最小间隔（14 天） 且 净收益 > 0
最小间隔     = 14 天：低于该值直接建议暂不清洗，仲裁不得推翻（行业实践下限）
```

**为什么加最小间隔**：2 天就建议再洗在现实中不成立。频繁清洗会增加人工与水资源成本、提高组件划伤风险，行业实践通常以 2 周为下限。

参数全部在 `backend/data/pv_config.json` 中可调，页面已声明为估算模型。

## Agent 职责

| Agent | 目标 | 可投反对票的情形 |
|---|---|---|
| 气象分析官 | 判断作业窗口 | 降水或风速超限 |
| 污损评估官 | 量化发电损失 | 损失率低于 5% |
| 收益核算官 | 确认收益覆盖成本 | 净收益为负 |
| 运维调度官 | 给出执行窗口 | 不投票，只提议 |
| 仲裁官 | 冲突时给折中 | 全站不经济时改为分区清洗 |
| 评审主席 | 判断是否执行 | 汇总阻塞项 |

## 协商机制

1. 气象、污损、收益三个 Agent 独立评估，可投反对票。
2. 天气不满足时，直接延后并给出复评窗口。
3. 收益或污损不满足时，仲裁官给出"分区清洗"折中方案，第二轮重新评估。
4. 评审主席汇总，输出最终决策与收益明细。

## 评分点对应

| 评分维度 | 对应实现 |
|---|---|
| 创新性与价值 30 | 新疆光伏沙尘场景、可算账的清洗决策、公开数据驱动 |
| 技术实现 25 | 多 Agent 协商、流式事件、真实数据接入、失败降级 |
| 码道使用深度 25 | 需在 `codearts_proof/` 留存全过程记录 |
| 工程质量 12 | 零构建前端、一键启动、接口分层、参数可配置 |
| 交付规范 8 | 五件套结构与说明文档 |

## 交付前必须补

1. **码道使用痕迹**：从开发第一天开始留存，不要事后补。
2. **参数核对**：清洗成本、电价、效率按目标电站实际值调整，并在 PPT 中说明来源。
3. **现场兜底**：演示用"演示样例"模式，避免现场网络异常。

## 三分钟演示脚本

1. 选择"演示样例"，装机 20MW、上次清洗 20 天。
2. 展示 Agent 拉取数据并给出：辐照 5.8、PM10 135、污损损失 15%。
3. 收益官算出净收益并给出回本周期。
4. 调度官给出执行窗口。
5. 把"上次清洗天数"改成 2，展示污损官反对、仲裁官提出分区清洗、第二轮收敛。
6. 切换到"实时公开数据"，证明数据是真实拉取的。

## 已知限制

- 污损模型为简化估算，未接入实测 IV 曲线。
- 辐照为公开气象再分析/预报值，与站点实测存在偏差。
- 未接入电力交易价格曲线，电价按固定值估算。
- 清洗成本按元/次配置，不同清洗方式差异较大。