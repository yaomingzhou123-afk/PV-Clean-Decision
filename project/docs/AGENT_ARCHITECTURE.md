# AGENT_ARCHITECTURE · 多 Agent 主决策链路架构

日期：2026-11-16（V3.0 第五阶段）
核心承诺：**七个 Agent 真实接入主决策 API**，不是展示层；关键计算由确定性 Python 执行，LLM 仅做审查增强，失败自动降级为纯规则链路。

---

## 一、调用顺序（主决策 API 实际执行路径）

```
POST /api/decide/stream
  → orchestrator.stream_decision()
      1. load_config（参数合并）
      2. 数据获取（MCP get_site_data 或直连 fetch_context）
      3. pv_model.compute_metrics（确定性计算：污损/经济/决策初值）
      4. agent_team.run_team(metrics, config)   ← 七个 Agent 顺序执行
         ① Weather Agent        → weather（天气/降雨/风速/辐照 + 数据来源与时间）
         ② Soiling Agent        → soiling（PM10/PM2.5/沙尘/无雨天数，标注 model_estimate）
         ③ PV Performance Agent → pv_performance（发电损失分析）
         ④ Economic Agent       → economics（复核确定性计算结果，不自行计算金额）
         ⑤ Safety Agent         → safety（检查用户配置阈值，必要时否决）
         ⑥ Critic Agent         → critic（规则审查 + 可选 LLM 增强）
         ⑦ Decision Agent       → decision（汇总，遵守安全否决，输出理由链）
      5. 事件流输出：每 Agent 两条事件（agent_result 结构化 + agent_speak 兼容）
      6. 第二轮：协商可视化 + 仲裁（Safety 否决时跳过仲裁）
      7. final 事件（含 agent_execution 全部结果）
```

## 二、Agent 统一结果结构

每个 Agent 输出（`agent_result` 事件与 `metrics.agent_execution.agents[]`）：

| 字段 | 说明 |
|---|---|
| agent_name | Agent 标识 |
| status | ok / error / skipped（结构校验失败标 error，不进入决策） |
| conclusion | 结论（含数据来源与时间说明） |
| evidence | 结构化证据：metric / value / threshold / unit / verdict |
| data_sources | 数据源元数据（source / data_kind / is_simulated / fetched_at / valid_time） |
| assumptions | 假设声明 |
| uncertainties | 不确定性声明 |
| recommendation | 建议（veto / approve / profitable / …） |
| confidence_type | **heuristic**（启发式评分）或 none；未经统计校准，绝不称真实概率 |
| confidence | 启发式评分值（0.6–0.99，规则推导，无随机） |
| inputs_read | 本 Agent 实际读取的输入快照（可追溯） |
| veto_type | 仅 Safety Agent：weather / interval / data_quality |

## 三、Critic Agent 的四类真实审查（规则层）

1. **计算复核**：净收益重新计算（horizon_revenue − cost − downtime），容差 2 元，不一致标 `calculation_error`
2. **结论矛盾**：Safety 已否决但 Weather 仍判窗口适合 → `contradiction`
3. **模拟数据误标**：数据源 is_simulated=true 但结论声称"实时" → `simulation_mislabeled`
4. **单位抽查**：rain=mm、wind=m/s、soiling=%、net=元、pm10=μg/m³ → `unit_error`

## 四、LLM 的角色与约束

| 项 | 设计 |
|---|---|
| 调用位置 | 仅 Critic 增强（把六 Agent 结论交 LLM 审查） |
| 次数上限 | `LLM_CRITIC_MAX_CALLS = 1`（防循环失控） |
| 输出校验 | 必须为严格 JSON `{"issues":[{"agent","issue","severity"}]}`；解析失败返回 None（跳过） |
| 失败降级 | LLM 不可用/超时/格式错 → `llm_enhanced=False`，规则 Critic 独立完成 |
| 禁止事项 | 不做数学计算、不产生天气/辐照/成本/污损数值、不直接改决策 |

## 五、Decision Agent 与安全否决

```
若 Safety veto（weather/interval/data_quality）：
    final_action = defer / hold / insufficient_data（按否决类型）
    且只允许比规则决策更保守（保守序：clean < hold < defer < insufficient_data）
否则：
    final_action = 规则引擎决策（与 pv_model 一步）
```

`decision_trace` 输出五因子理由链：安全否决 → 污损水平 → 经济性 → 基础规则决策 → Critic 审查。

## 六、异常处理

| 异常 | 行为 |
|---|---|
| Agent 输出结构不合规 | `_validate_result` 返回 None → 标 error + skipped，不进入决策 |
| LLM 不可用 | llm_enhanced=False，规则链路独立完成 |
| LLM 输出非 JSON | 解析失败，静默跳过 |
| 数据不足 | insufficient_data 短路，Critic 说明原因后直接结束 |
| MCP 不可用 | 回退进程内直连 |

## 七、验证证据（tests/test_agent_team.py，19 项）

- 主决策 API 实际调用 run_team（spy 断言 calls==1，agent_result 事件 ==7）
- 七 Agent 顺序执行、结构完整、读取统一 metrics
- Critic 识别真实注入的计算错误（net_gain 篡改 → calculation_error → reject）
- Critic 识别模拟数据误标（is_simulated + "实时"字样 → simulation_mislabeled）
- Safety 风速否决 / 间隔否决；Decision 遵守否决（veto_applied + defer）
- LLM 失败回退（llm_enhanced=False，final_action 不变）
- LLM 输出结构校验（非 JSON / 缺字段 / 错类型拒绝；合法 JSON 解析）
- 不合规 Agent 输出标 error
- confidence_type 全部 heuristic，无概率冒充
- Soiling 结论含 model_estimate 与"非传感器实测"
- decision_trace 五因子完整可追溯

运行方式：`cd /workspace/pv-agent && python3 -m pytest backend/tests -q`（当前基线 117 passed）