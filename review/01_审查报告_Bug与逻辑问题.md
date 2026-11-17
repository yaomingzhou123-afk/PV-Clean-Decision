# PV-Clean-Decision 全项目审查报告（只读 · 不含任何功能改动建议）

审查日期：2026-11-17
审查方式：3 路并行代码检视（决策链 / 数据源与协议层 / 前端与材料口径）+ 206 项测试实跑 + 华为云竞赛官方页面抓取
审查范围：backend 全部 27 个 Python 文件、frontend/index.html（1032 行）、presentation/readme 材料、官方提交规范

---

## 一、总裁决

**核心计算逻辑清晰，可以交付；但发现 2 个 P0 + 11 个 P1 缺陷，其中 2 个 P0 均为"静默出错"型，建议赛前修复（均为小改动，无需加功能）。**

| 维度 | 结论 |
|---|---|
| 单位换算（辐照 MJ→kWh、风速 m/s） | ✅ 全项目唯一换算点，无二次换算风险 |
| 四条核心公式量纲（净收益/污损/停机/回本） | ✅ 分子分母一致 |
| 决策优先级（insufficient > weather > interval > economics） | ✅ 三处实现一致 |
| 四种决策流转 | ✅ 无死角 |
| 测试基线 | ✅ 实跑 206 项全绿（29.61s，Python 3.12.5） |
| 材料核心数字（39,478 元 / 206 项 / 七 Agent / 14 天） | ✅ 与代码实测一致，旧值 41,975 无残留 |
| 编排层口径 | ⚠️ 存在"事件层与数据层打架"的双口径问题（见 P0/P1） |
| 工具层降级防线 | ❌ P0-2 存在绕过路径 |

---

## 二、P0（必须修，静默出错型，修复量均小）

### P0-1 MCP 客户端超时后请求/响应永久错位
- 位置：`backend/mcp_client.py:71-73`（根因）+ `backend/agent_loop.py:33-35`（放大器）
- `request()` 从不校验响应 `id` 与请求 `id` 匹配。一次超时后残留响应留在队列，之后每次调用错位一格、永不自愈——`search_knowledge` 的结果可能被当作 `get_site_data` 返回喂给 LLM。
- 触发条件：问答链 MCP 会话复用中任一次 TimeoutError。`MCPClient(timeout=30)` 硬编码，`DS_TIMEOUT ≥ ~14.7s` 时稳定复现。
- 现有测试只验证"超时可抛出"，未覆盖错位。

### P0-2 `calc_economics` 的 mode 与 config.scenario 解耦，降级防线可被绕过
- 位置：`backend/mcp_server.py:113-129` + `backend/agent_tools.py:77-80`（入口）；`backend/pv_model.py:293-296`（防线）
- 数据模式由 `args["mode"]` 决定，而"不基于模拟数据决策"防线只检查 `config["scenario"]=="live"`。demo 场景下 LLM 自主传 `mode="live"` + 接口失败降级 → 用模拟数据正常算出清洗决策，action 不是 insufficient_data。
- mcp_server 与 agent_tools 两条路径同时存在此分叉。主链路 orchestrator 因 scenario 与 mode 同源而侥幸不受影响。

---

## 三、P1（赛前应修）

### 后端编排层
1. **Critic reject 降级 hold 后，最终 `metrics["decision"]["action"]` 不回写，仍是 clean**——`agent_team.py:524-574` 只写事件层 `final_action`，第二轮协商通过则不修订。LLM 开启（比赛演示环境常配 LLM）即可现场出现"clean 与 hold 并存"的自相矛盾输出，评委可直接撞见。
2. **weather 否决路径的 defer 决策丢失复评窗口**——`orchestrator.py:220-233` veto 分支旁路了 defer_plan，`decision.window=None` 与同 metrics 的 `weather.best_date` 并存；两条 defer 产出路径字段 shape 不一致。
3. **get_site_data 双实现默认 mode 相反**——MCP 端默认 `"live"`（`mcp_server.py:81`），进程内默认 `"demo"`（`agent_tools.py:57`）。同名工具两套默认行为。
4. **loss_pct 参数在 dispatch 路径被静默忽略**——`agent_tools.py:63-67` 完全不读 args，MCP 路径生效，两条路径同一请求不同结果。
5. **llm.raw_chat 吞掉所有异常且零日志**——`llm.py:62-63`，401/DNS/超时全部折叠为 None，排障不可诊断（回退本身安全，不产虚构数字）。
6. **fetch_json 对确定性 4xx 也按网络错误重试**——`data_sources/base.py:30-43`，400/403 白耗一次请求+0.6s。

### 前端
7. **影响曲线只渲染 4/9 组**——`frontend/index.html:1777-1783` 只挑 pm10/price/cleaning_total/dry_days 渲染，后端 `_impact()` 实际返回 9 组，pm2_5/recovery_efficiency/expected_rain_mm/capacity_mw/tilt_angle_deg 5 组静默丢弃。
8. **后端中途断流被误判"已完成"**——`frontend/index.html:1345-1359`，orchestrator 的 run_team 段无捕获、异常断流后前端保存未经仲裁的中间态快照进历史，无任何错误提示。
9. **loadHistory 缺 Array.isArray 校验**——`frontend/index.html:1162-1165`，非数组 localStorage 值会 TypeError 冒泡成"配置加载失败"，误导排查（对照 loadSimCustom 有完整校验，双标）。

### 答辩材料口径（比赛诚信风险）
10. **评委问答 Q32"177 项 MCP 测试"自相矛盾**——`评委问答参考.md:195`，Q29 明说 MCP 协议 19 项、总数 206。177 是历史旧基线。应改为"206 项测试（含 19 项 MCP 协议专项）"。
11. **演讲稿 P9"九组参数影响曲线"与现场 UI 只有 4 组冲突**——`逐页演讲稿.md:91`（与前端问题 7 同源）。要么改口"四组主要参数曲线（系统可输出九组）"，要么赛前修前端渲染。
12. **readme/README.md 架构章节停留在旧六 Agent 版本**——16 行"四个 Agent"、143-159 行旧职责表/旧协商机制，与同文件 27 行"七个 Agent"自我矛盾，与代码/PPT 三套口径打架。README 是交付核心文档，风险最高。

---

## 四、P2（不阻断交付，择机清理）

**后端逻辑/边界**
- 第二轮旧协商层 weather/interval 分支为不可达死代码（`orchestrator.py:253-267`），两套第二轮机制并存误导维护
- run_team 死变量 rule_issues、未被消费的 needs_second_round（`agent_team.py:627、649-652`）
- PVGIS 月份取服务器本地时区而非 Asia/Shanghai；缓存键不含月份可跨月返回上月 E_d（`pvgis_source.py:14-15、44-47`）
- pv_model 读不存在的 "cached" 键，pvgis.cached 永远 False（`pv_model.py:400`）
- 经济结论文案可输出"回收期 None 天"（days_since_clean=0 时可达，`agent_team.py:283`）
- wind_max 实为 3 天/72h 口径，但全部文案声称"未来 48 小时"（`pv_model.py:360-361`）
- 团队事件 margin_ratio 硬编码 0.5（伪造裕度，`agent_team.py:690`）
- apply_partial 只排除 weather_block 不检查 interval_block（`agents.py:344-352`，当前主链不可达）
- 0<net<0.5 元窗口内"clean 决策 vs 净收益报告 0 元"矛盾（`pv_model.py:373/410`）
- cache_set 的 `ttl or DS_CACHE_TTL` 把显式 ttl=0 变 6h（`base.py:67`）
- search_knowledge 校验双标：MCP 严、dispatch 松（top_k=0/-5 静默错切）
- env_loader 不支持 export 前缀、引号剥离有损；LLM_TIMEOUT 非法值导致整个后端起不来（模块导入期解析）
- NASA POWER 为未接线第三处残留实现（开关导入期固化）
- MCP unknown tool 错误码用 -32601 而非 -32602；坐标 44.01/87.31 硬编码与 config 巧合一致

**前端**
- pipeline_error 后 timelineHint 永久停留"协商中…"（`index.html:1316/1357`）
- 移动端隐藏规则是死 CSS，顶栏窄屏未收纳（`index.html:356`）
- 历史回放对旧记录缺失字段填入 "undefined"（`index.html:1192-1193`）
- agent_decision 二轮修订渲染成两张同名仲裁卡，second_round_revision 字段未消费（`index.html:1413-1417`）
- NDJSON 读流结束时残留 buf 不解析（当前后端每行带 \n 不触发）
- run() 无 AbortController，LLM 慢时 UI 锁死数十秒
- kbChips href 不过滤 javascript: 伪协议（数据源本地固定，风险≈0，XSS 其余全部已修复）
- 死状态：state.inputs、state.sim.values 从未被消费

**材料小口径**
- 知识库"36 条"→实际 37 条（Q31，`评委问答参考.md:191`）
- "13 个 REST + 2 个流式"→实际 `/api/*` 共 14 个 = 12 REST + 2 流式（演讲稿 P4）
- readme 演示脚本步骤 5 描述与当前代码行为不符（days=2 走 Safety 间隔否决，非"分区+二轮收敛"）
- readme 数据源表漏列 PVGIS（主链三大源之一）
- "每条数据九个元数据字段"可自洽（前端 dq-table 恰 9 列）但 API 原样字段 13 个，建议统一数法

---

## 五、专项核查通过项（答辩硬底气）

| 项 | 结论 |
|---|---|
| XSS | 30 余处 innerHTML 插值点全覆盖 esc() 转义；唯一理论残留为 href 伪协议（风险≈0） |
| NDJSON 协议前后端字段 | 14/14 事件全覆盖；insufficient_data / mcp_error / agent_error 均有处理 |
| 竞态防护 | 按钮 disabled 防重入 ✓、模拟请求 reqId 防乱序 ✓、防抖协调 ✓ |
| 材料核心数字 | 39,478 / 1.2 天 / 15.0% / 95.1 MWh / 206 项 / 七 Agent / 14 天 / 12 场景 / 17 参数 / 3 策略 / P0×10+回归 28——全部实测复现 |
| CI | GitHub Actions，Python 3.10-3.12 矩阵 + 前端 JS/HTML 检查，属实 |
| MCP 子进程生命周期 | close 幂等 + terminate→wait→kill 链完整，无稳定僵尸/泄漏路径 |
| LLM 三条回退 | 均不产出虚构数字（安全性通过，可诊断性 P1-5 待修） |

## 六、官方交付结构 Gap（重要）

官方要求 zip 内五个目录：`ppt/` `project/` `video/` `codearts_proof/` `readme/`。当前仓库为 `presentation/`（含 PPT+视频混放）等命名，**提交前必须重组打包目录结构**，详见《04_提交标准对照.md》。
