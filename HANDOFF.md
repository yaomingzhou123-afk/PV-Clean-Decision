# HANDOFF · 明日恢复上下文入口

> 给明天的码道会话：请先读本文件与本目录 `codearts_proof/` 下的 8 个记录文件，即可恢复全部上下文。

## 项目

疆光 · 光伏电站沙尘清洗决策 Agent
参赛：2026 华为开发者大赛·智能体创新赛（昌吉学院站）
代码：`/workspace/pv-agent/`（备份：`/workspace/pv-agent.zip`）

## 硬截止

- **报名 + 组队：11-14 15:59（明日截止，最优先！）**
- 作品提交：11-20（每队每天限 1 次）
- 决赛：12-02，第一名直通全国总决赛

## 启动命令

```bash
cd /workspace/pv-agent && bash run.sh   # http://127.0.0.1:8001
cd backend && python -m pytest tests -q  # 31 项测试应全绿
```

注意：沙箱环境可能被重置，启动前先 `pip install -r requirements.txt`（版本已钉）。

## 六阶段进度（截至 11-14）

| 阶段 | 状态 |
|---|---|
| 1 架构扫描与缺陷清单 | ✅ 完成 |
| 2 PVGIS 接入、参数校验、质量分级、测试 | ✅ 完成并验收 |
| 3 Agent 置信度 + 结构化证据 + 输入快照 + 仲裁比例动态化 + defer 独立评审 | ✅ 完成并验收（23 项测试全绿，2026-11-14） |
| 4 前端：XSS 修复、仪表盘、SVG 趋势图、localStorage 历史、md 报告导出、移动端 | ✅ 完成并验收（三档视口 0 横向滚动、0 报错、导出可用，2026-11-14） |
| 4.5 RAG 知识库（评分细则点名项） | ✅ 完成并验收（37 条/6 类，BM25 检索，5 Agent 引用全覆盖，31 项测试，2026-11-14） |
| 4.6 MCP 工具层（评分细则点名项） | ✅ 完成并验收（JSON-RPC over stdio，3 工具，主链路真实调用，38 项测试，2026-11-14） |
| 4.7 Function Calling | ✅ 完成（LLM 工具循环 4 步上限 + 前端面板 + 自检脚本，47 项测试；真实 Key 正例待现场验证） |
| 5 API/Agent 测试、结构化日志、Windows 说明 | ⏸️ 下一步 |
| 6 沙箱部署（实名已通过）、五件套打包 | ⬜ |

## 阶段 5 具体范围（下一步）

1. 新增 `backend/tests/test_api.py`：FastAPI TestClient 覆盖 /api/health、/api/config、非法参数 422、流式事件序列
2. 结构化 JSON 日志：数据拉取、降级、决策完成三个关键节点
3. Windows 启动说明（PowerShell + venv 等效命令）
4. README 补充前端结构与导出说明
涉及文件：`backend/main.py`、`backend/tests/`、`readme/README.md`

## 已确认的设计决策（勿改）

- 历史决策记录：localStorage（前端）
- 报告导出：Markdown 下载
- 测试框架：pytest（已加依赖）
- 置信度：规则推导
- 理论发电量：live 用 PVGIS 月均值，作业窗口用 Open-Meteo 三天预报（口径分离）
- 规则引擎承载全部决策计算，LLM 仅做总结增强
- 演示样例模式必须保留，断网可跑
- RAG 用本地 BM25（零依赖），未核实条目必须在界面标注"待核实"，不冒充权威
- 下一步按评分细则补强：MCP 工具层 → Function Calling（可选）→ 多 Agent 辩论/投票

## 团队待办（非代码）

1. ⚠️ 今日 15:59 前：队友实名 + 报名 + 加入队伍（逾期无法提交，务必先办）
2. codearts_proof/screenshots/：4 类真实截图（会话/生成/测试/运行界面）
3. 从码道导出关键对话存档
4. 检索 1–2 条政府采购网光伏清洗中标公告，替换清洗成本占位依据
5. PPT、3 分钟视频（脚本见 readme/README.md 末尾）

## 关键事实速查

- PVGIS 11 月 E_d=3.79 kWh/kWp（ERA5 2005–2023），接口 4.2s
- demo 场景净收益 41,975 元（20MW/20 天/0.25 元/4000 元）
- 缺陷修复记录 9 条：见 codearts_proof/04_调试与Bug修复记录.md
- 阶段三验收数据：agent_input 4 条全覆盖、confidence 5/5、仲裁比例 42% 随污损动态推导、defer 独立评审 conf 0.67
- 官方提交规范：zip 内五件套 ppt/ project/ video/ codearts_proof/ readme/
