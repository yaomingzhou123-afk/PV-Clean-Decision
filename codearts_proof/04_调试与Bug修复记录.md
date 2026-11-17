# 04 调试与 Bug 修复记录

以下全部为真实发生并通过回归验证的修复，每条含现象、定位、修复、验证。

> 注：BUG-01/02 为早期文旅原型（v1）的修复，保留以证明协商机制验证过程；BUG-03 起为光伏项目（v2+）的修复。

## BUG-01 协商轮次显示错误

- 现象：前端显示"方案 v4"，但实际仅第 2 轮
- 定位：`build_plan()` 内部对 `bb.version` 自增，分区修订每调用一次递增一次
- 修复：事件流改用协商轮次 `round_no` 作为版本号
- 验证：demo 场景显示 v1，修订场景显示 v2

## BUG-02 预算削减候选选了免费点

- 现象：超出预算时建议削减"努尔加大峡谷"（0 元景点），削减后成本不变
- 定位：性价比排序按 `price/duration` 升序，免费点比值为 0 排最前
- 修复：改为仅在收费点中按 `(非必去优先, 单价高优先)` 排序，并循环削减直至预算内
- 验证：超预算场景 2 轮内收敛

## BUG-03 停机损失单位错误

- 现象：停机损失 23124 元，约为日发电收入 4 倍，明显不合理
- 定位：误将"日发电量"当"小时发电量"与停机小时相乘
- 修复：改为 `理论日发电量 ÷ 24 × 停机小时 × 电价 × 1000`
- 验证：20MW 电站 4 小时停机损失约 3963 元，与日收入比例合理

## BUG-04 仲裁优先级错误

- 现象：天气与经济同时反对时先做分区清洗，但天气仍阻塞，最终 forced 未收敛
- 定位：分支判断 economics 在 weather 之前
- 修复：weather 阻塞时直接 defer 并独立评审，不再进入分区清洗
- 验证：实时模式（有降雨）2 轮内收敛，forced=False

## BUG-05 demo_context 缺字段致测试失败

- 现象：pytest `KeyError: 'fetched_at'`，13 通过 1 失败
- 定位：第二阶段统一上下文时间戳字段时，demo_context 顶层遗漏
- 修复：补 `fetched_at`
- 验证：14 项全绿

## BUG-06 启动路径依赖工作目录

- 现象：从项目根启动 `uvicorn backend.main:app` 时前端 404
- 定位：`FileResponse("../frontend/index.html")` 硬编码相对路径
- 修复：改为基于 `__file__` 的绝对路径
- 验证：任意目录启动均可访问

## BUG-07 参数未校验导致 500

- 现象：传入非法值时 `float()` 抛异常，SSE 流中断
- 修复：pydantic 请求模型（范围约束）+ `validate_config` 边界检查 + ValueError 全局处理返回 400
- 验证：capacity=-5 返回 HTTP 422 及字段级错误

## BUG-08 置信度公式漏封顶

- 现象：单测断言 `0.6 <= confidence <= 0.99` 失败，实际算出 1.0
- 定位：`_confidence` 为 `0.6 + 0.4 * ratio`，ratio 封顶 1.0 时结果恰为 1.0，超出设计上限
- 修复：改为 `min(0.99, 0.6 + 0.4 * ratio)`
- 验证：23 项测试全绿

## BUG-09 dict 键解包笔误

- 现象：`critic_defer_review` 抛 `ValueError: too many values to unpack`
- 定位：误写 `d, w = m["decision"]`——这是在解包 dict 的键（6 个）而非取字段
- 修复：改为 `d = m["decision"]`、`w = m["weather"]`
- 验证：defer 独立评审单测通过，live 场景 critic 二轮复核输出 confidence 与 evidence

## 环境事件

- 开发环境曾被外部重置（fastapi 缺失、uvicorn 版本漂移），按钉版本的 requirements.txt 重装后恢复。此事件验证了依赖钉版本对可复现性的必要性。

## P0-1 MCP 客户端超时后请求/响应永久错位（v3.1，2026-11-17）

- **开发目标**：修复 MCP 会话复用中超时后响应错位的静默错误
- **给 AI 的 Prompt**："检查 mcp_client.py 的 _send 方法，超时后残留响应留在队列会导致后续请求错位，请修复并加验证测试"
- **现象**：一次 MCP 超时后，残留响应留在队列，之后每次 request() 错位一格、永不自愈——search_knowledge 的结果可能被当作 get_site_data 返回喂给 LLM
- **根因定位**：`mcp_client.py:73` `_send()` 读响应时不校验 `resp["id"]` 与请求 `id` 匹配，直接返回队列里下一行
- **修复**：`_send` 改为 while 循环，丢弃 id 不匹配的残留响应并记录 warning，直到拿到匹配响应或超时
- **修改文件**：`backend/mcp_client.py`（+6 行）
- **验证测试**：`test_p0_1_client_discards_stale_response_by_id_mismatch`（构造先吐 id=999 残留再吐正确响应的 server，验证 client 丢弃残留）+ `test_p0_1_client_still_raises_on_real_timeout`（真超时仍抛 TimeoutError）
- **验证结果**：210 项测试全绿

## P0-2 calc_economics mode 与 config.scenario 解耦绕过降级防线（v3.1，2026-11-17）

- **开发目标**：修复 demo 场景下 LLM 传 mode=live + 接口降级时用模拟数据给出 clean 决策的诚信风险
- **给 AI 的 Prompt**："calc_economics 的 mode 由 args 决定但降级防线只查 config.scenario，demo 场景传 mode=live + fallback 数据会绕过防线，请修复"
- **现象**：demo 场景下 LLM 自主传 mode="live" + 接口失败降级 → 用模拟数据正常算出 clean 决策，action 不是 insufficient_data
- **根因定位**：`mcp_server.py:115` 和 `agent_tools.py:78` 用 args["mode"] 决定数据模式，但 `pv_model.py:293` 防线只检查 `config["scenario"]=="live"`。mode=live + scenario=demo 时防线不触发
- **修复**：mode 与 scenario 不一致时用浅拷贝 `{**config, "scenario": mode}` 同步，防线正确触发
- **修改文件**：`backend/mcp_server.py`（+3 行）+ `backend/agent_tools.py`（+3 行）
- **验证测试**：`test_p0_2_dispatch_mode_live_with_demo_scenario_triggers_insufficient`（断言 action==insufficient_data）+ `test_p0_2_dispatch_demo_mode_still_works`（正常 demo 路径不受影响）
- **验证结果**：210 项测试全绿，不破坏正常 demo 路径
