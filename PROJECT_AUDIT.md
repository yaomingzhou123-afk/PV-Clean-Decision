# PROJECT_AUDIT · PV-Clean-Decision 全面审查报告

审查人：首席技术架构师（码道）
审查日期：2026-11-15
审查方式：逐文件实读 + 49 项测试实跑 + 接口实测
版本基线：工作区文件（对应远程 d9cf4e2 内容），本地 Git HEAD 9efb1f2

---

## A. 当前架构

```
浏览器（frontend/index.html，零构建 SPA，1032 行）
   │  POST NDJSON 流式
   ▼
FastAPI（backend/main.py）
   ├─ /api/health          健康检查（返回 rule/llm 模式）
   ├─ /api/config          读取 pv_config.json
   ├─ /api/decide/stream  主决策流（清洗决策 Tab）
   └─ /api/agent/stream   Agent 问答流（Function Calling Tab）
   │
   ├─ 决策链 orchestrator.stream_decision()
   │    1. load_config 合并参数（pydantic 校验过）
   │    2. MCP 优先取数：MCPClient 子进程 → tools/call get_site_data
   │       失败回退：demo_context() / fetch_context()（进程内直连）
   │    3. MCP 优先计算：tools/call calc_economics → compute_metrics
   │    4. 四个评审 Agent（纯规则函数）逐个出意见
   │    5. 评审主席裁决；间隔阻塞一票否决；冲突进仲裁（分区清洗）或延后
   │    6. 最多 2 轮；LLM 仅生成 ≤100 字总结（可选，失败回退固定话术）
   │
   └─ 问答链 agent_loop.stream_agent()
        LLM（OpenAI 兼容，默认华为云 MaaS /v2）
        + 3 个工具 schema（get_site_data / search_knowledge / calc_economics）
        → 模型自主决定调用（最多 4 步）→ 工具经 MCP 执行 → 自然语言回答

MCP 层：mcp_server.py（JSON-RPC 2.0 over stdio，真实协议实现）
        mcp_client.py（子进程客户端，Windows 下强制 PYTHONUTF8）
数据层：weather.py（Open-Meteo ×2 + PVGIS + 降级样例）
        kb/（37 条知识库 + 纯 Python BM25）
配置层：pv_config.json（含 sources 参数依据）+ .env（LLM 凭证，已 gitignore）
```

## B. 当前功能清单

| 功能 | 状态 | 验证方式 |
|---|---|---|
| 清洗决策全链路（demo） | ✅ 正常 | 实测：clean / 41,975 元 / 回本 1.1 天 |
| 最小清洗间隔 14 天否决 | ✅ 正常 | 实测：2 天→hold，14 天→clean |
| 多 Agent 协商（4 评审 + 主席 + 仲裁） | ✅ 正常 | 事件流 5 发言全带置信度/证据 |
| RAG 知识引用 | ✅ 正常 | 5/5 发言带 kb_refs，未核实条目标黄 |
| MCP 工具层 | ✅ 真实 | JSON-RPC 握手/tools/list/tools/call 实测通过 |
| Function Calling 问答 | ✅ 本机实测通过 | 模型自主调用 search_knowledge，引用 KB-A02/A06 |
| 三级降级（live→fallback→demo） | ✅ 正常 | 质量徽章四态如实显示 |
| 决策驾驶舱前端 | ✅ 正常 | 状态灯/Tab/KPI/骨架屏，0 控制台错误 |
| Markdown 报告导出 | ✅ 正常 | 含公式、参数来源、Agent 依据 |
| 历史决策 localStorage | ✅ 正常 | 最近 20 条，可回放 |
| 实时数据（live） | ⚠️ 依赖网络 | 沙箱网络曾失败，本机未复测 |
| 公网部署 | ❌ 未完成 | 沙箱配额不足 |

## C. 当前数据源清单

| 数据 | 来源 | 真实性 | 标注 |
|---|---|---|---|
| 辐照/降水/风速/云量 | Open-Meteo Forecast | 真实接口 | source=open-meteo, quality=live |
| PM10/PM2.5/沙尘 | Open-Meteo Air Quality | 真实接口 | source=open-meteo-air |
| 理论发电量 E_d | PVGIS v5_3（ERA5 2005–2023） | 真实接口，6h 内存缓存 | source=pvgis, cached 标记 |
| 演示数据 | DEMO_FORECAST/DEMO_AIR（内置） | 模拟，明确标注 | source=demo, quality=demo |
| 降级数据 | FALLBACK_FORECAST/FALLBACK_AIR | 模拟，明确标注 | source=fallback |
| 知识库 | 37 条 jsonl（23 条来源已核实） | 静态文件 | verified 字段如实标注 |
| LLM | 华为云 MaaS deepseek-v4.1-flash-1017 | 真实调用（本机验证） | mode=llm/rule 如实显示 |

## D. 当前算法与公式

| 项 | 公式 | 参数来源 |
|---|---|---|
| 污损损失率 | `min(max_loss, (base_rate + max(0, PM10−ref)×factor) × days)` | IEA PVPS 区间，config.soiling |
| 理论日发电量 | PVGIS：`capacity_mw × E_d`；降级：`capacity_mw × 辐照 × efficiency` | PVGIS / config.economics |
| 日恢复收益 | `理论发电 × 损失率 × 1000 × 电价` | config |
| 停机损失 | `理论发电 ÷ 24 × 停机小时 × 电价 × 1000` | config |
| 净收益 | `日收益 × horizon − 清洗成本 − 停机损失` | config |
| 天气阻塞 | `rain_next48 ≥ 1mm 或 wind_max ≥ 12m/s` | config.safety |
| 间隔否决 | `days_since_clean < 14` | config.soiling |
| 决策优先级 | weather_block > interval_block > economics | 代码实现 |
| 分区比例 | `0.3 + 0.4 × (loss_ratio / max_loss)` | config.negotiation |
| 置信度 | `min(0.99, 0.6 + 0.4 × 偏差比)`，确定性无随机 | 代码实现 |

## E. 已发现问题（P0 > P1 > P2）

### P0（必须修，影响正确性）—— ✅ 已于 V3.0 阶段二全部修复（2026-11-15）

1. ~~**辐照单位未换算**~~ ✅ 已修复：`_daily_to_raw_days` 内 `mj_to_kwh()` 完成唯一一次 ÷3.6
2. ~~**风速单位未换算**~~ ✅ 已修复：请求参数 `wind_speed_unit=ms` 源头统一
3. ~~**sanitize_days 上限口径冲突**~~ ✅ 已修复：输入统一 kWh/m² 后 0–12 校验口径正确，缺失/越界剔除
4. ~~**dust 缺失静默污染**~~ ✅ 已修复：dust 缺失置 None，不再混入 fallback 值

### P1（应修，影响可信度/流程）

5. **Git 状态分叉**：本地 HEAD 9efb1f2 落后远程 d9cf4e2，工作区含未提交修改（内容与远程一致）。环境反复重置导致，需 fetch + 对齐 + push 固化。
6. **无鉴权、无限流**：API 完全公开（比赛不扣分；企业级/公网部署 P0）。
7. **MCP 每请求起子进程**：约 100ms 开销 + 静默吞异常（`except: pass` 后回退直连，无日志，失败不可见）。
8. **无结构化日志**：全项目零 logging，排障只能靠 print 和前端事件。

### P2（可延后）

9. **uvicorn 绑死 127.0.0.1**：公网/容器部署需改 0.0.0.0（main.py:107）。
10. **LLM 失败静默回退**：总结失败回退固定话术，前端仅 mode 徽章可辨，无显式告警事件。
11. **speak() 每次全量 BM25 检索**：37 条规模下可忽略，扩容后需缓存。
12. **PVGIS 缓存仅内存**：重启丢失（6h TTL，可接受）。
13. **pv_model 中 avg_irradiance 重复计算两次**（60–68 行，纯冗余）。
14. **无 CI**：测试靠手动执行。

## F. 测试现状

- **数量：66 项，全部真实通过**（V3.0 阶段二实跑 `66 passed in 2.38s`；审查基线时为 49 项）
- 分布：pv_model 12（含间隔 2）/ weather 4 / agents 9 / kb 8 / mcp 7 / llm 5 / agent_loop 4
- 覆盖：公式、边界校验、降级链、置信度确定性、MCP 协议（握手/未知方法/解析错误）、RAG 检索、间隔否决
- **缺口：无任何单位换算测试**（P0-1/2/3 因此漏网）；无 API 层 TestClient 测试；无并发测试
- 运行方式：`cd backend && python -m pytest tests -q`

## G. 建议升级方案（V3.0，按优先级）

1. **修单位（半天，最高优先）**：fetch_forecast 内 `MJ÷3.6→kWh`、`km/h÷3.6→m/s`（或请求参数直接声明 `windspeed_unit=ms`、辐照换算），同步修 sanitize 上限口径；补 4 项单位回归测试（含"夏季 20 MJ/m² 不被剔除"）。
2. **修 dust 污染（10 分钟）**：dust 缺失时置 None 并在 data_quality 标注，或整体降级。
3. **结构化日志（半天）**：logging JSON 化，覆盖数据拉取/降级/MCP/LLM 四类节点。
4. **Git 固化（10 分钟）**：fetch + reset --soft origin/main + commit + push，之后每次改动即推。
5. **API 测试（半天）**：TestClient 覆盖 422/400/流式事件序列。
6. **鉴权与限流（1 天，公网前置条件）**：API Key 头 + slowapi。
7. **MCP 常驻（1 天，可选）**：单例子进程复用 + 失败显式事件。
8. **企业级路线（决赛后再做）**：OBS 存历史/报告 → APIG 网关 → FunctionGraph 工具云函数化 → 容器化多 worker。

## H. 需要你提供的配置或权限

| 项 | 用途 | 紧急度 |
|---|---|---|
| 无 | P0 单位修复不需要任何新权限 | — |
| 华为云 OBS 凭证（若做云存储） | 历史决策上云 | 决赛加分项，非必需 |
| 公网部署资源（沙箱错峰或 ECS） | 在线演示地址 | 初赛不需要 |
| LLM Key 已在你本机 .env | 云端无法验证 Function Calling 现状 | 云端验证时需提供 |

---

## 审查结论

**核心资产完好**：49 项测试、MCP 真实协议、RAG 可追溯、降级链诚实标注、业务规则（14 天间隔）合理——这些是答辩的硬底气。

**P0 单位缺陷已于 V3.0 阶段二修复**（2026-11-15）：辐照 ÷3.6 唯一转换、风速源头 m/s、缺失值剔除不参与计算、dust 不再污染。66 项测试全绿，逐公式审查与行为变更见 `docs/UNIT_AND_MODEL_FIXES.md`。live 模式恢复可信。

**宣传口径提醒**：六个 Agent 是确定性规则函数（非 LLM 自主体），Function Calling 问答链才是 LLM 驱动。答辩话术应表述为"规则引擎保证决策可复现，LLM 负责工具编排与总结"——这是设计优点，不要被动变成"假 Agent"质疑点。