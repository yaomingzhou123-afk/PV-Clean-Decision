# UNIT_AND_MODEL_FIXES · V3.0 第二阶段修复记录

日期：2026-11-15
范围：底层数据单位、缺失值处理、计算口径审查
约束遵守：未改前端、未加无关功能、全部测试真实执行

---

## 一、修复清单（对应 PROJECT_AUDIT P0-1 ~ P0-4）

| # | 问题 | 修复方式 | 涉及文件 |
|---|---|---|---|
| P0-1 | 辐照 MJ/m² 当 kWh/m² 用（虚高 3.6 倍） | `_daily_to_raw_days` 内 `mj_to_kwh()` 完成**全项目唯一一次** ÷3.6 | weather.py、utils/units.py |
| P0-2 | 风速 km/h 当 m/s 用（阈值必触发） | 请求参数显式声明 `wind_speed_unit=ms`，源头统一，不做二次转换 | weather.py |
| P0-3 | sanitize 上限 12 与 MJ 输入口径冲突 | 输入已是 kWh/m² 后，0–12 校验口径正确；夏季 20 MJ/m²（=5.6 kWh/m²）不再被误剔除 | weather.py、utils/units.py |
| P0-4 | dust 缺失静默填 fallback 值 80 且标 live | dust 缺失置 `None`，不再混入模拟值 | weather.py |

## 二、全项目单位约定（唯一口径）

| 物理量 | 全项目统一单位 | 转换发生位置 | 说明 |
|---|---|---|---|
| 辐照 | **kWh/m²**（日累计） | `weather._daily_to_raw_days`（÷3.6，仅此一处） | Open-Meteo 原始为 MJ/m² |
| 风速 | **m/s** | Open-Meteo 请求参数 `wind_speed_unit=ms`（源头） | `kmh_to_ms()` 仅作为工具函数保留，主链路不调用 |
| 降水 | **mm**（日累计） | 不转换 | 接口原生 mm |
| PM10 / 沙尘 | **µg/m³** | 不转换 | 接口原生 |
| 发电量 | **MWh/日** | pv_model | PVGIS E_d 单位 kWh/kWp，×MW 数值即 MWh |
| 电价 / 金额 | **元**、**元/kWh** | 不转换 | — |
| 时间 | **天 / 小时** | 不转换 | — |

**禁止事项（已落实）**：任何模块不得再次对辐照 ÷3.6 或对风速做 km/h 换算；`test_no_double_conversion_in_pipeline` 用管道级测试锁死该约定。

## 三、逐公式审查（输入 / 输出 / 单位 / 适用条件 / 边界）

### 1. 辐照数据处理
- 输入：Open-Meteo `shortwave_radiation_sum`（MJ/m²）
- 转换：`kWh/m² = MJ/m² ÷ 3.6`（`utils.units.mj_to_kwh`）
- 校验：`valid_irradiance_kwh`，范围 [0, 12] kWh/m²；None/非数字/负数/越界 → **剔除该天，不参与正式计算**
- 输出：`metrics.weather.avg_irradiance`（kWh/m²）
- 边界说明：12 kWh/m² 约为地表日辐照物理上限；0 合法（极端阴天）

### 2. 发电量估算
- PVGIS 路径：`theory_mwh_day = capacity_mw × E_d`；E_d 单位 kWh/kWp，与 MW 相乘数值即 MWh（1 MW × 1 kWh/kWp = 1 MWh）
- 降级路径：`theory_mwh_day = capacity_mw × avg_irradiance(kWh/m²，近似峰值日照小时) × efficiency`
- 输出：MWh/日
- 边界：capacity ∈ (0, 5000] MW、efficiency ∈ (0, 1]（`validate_config` 强制）

### 3. 污损率估算
- 输入：PM10（µg/m³）、距上次清洗天数、config 参数
- 公式：`loss = min(max_loss, (base_rate + max(0, PM10 − ref) × factor) × days)`
- 输出：无量纲比率（loss_ratio）与百分比（loss_pct）
- 边界：封顶 `max_loss=15%` 防外推失真；PM10 低于基准不加增量
- 已知防御点：`estimate_soiling` 中 PM10 缺失时回退基准值——实际不会触发（`fetch_air` 层 PM10 为空已整体降级），保留为防御代码

### 4. 清洗收益
- 公式：`daily_revenue = theory_mwh_day × loss_ratio × 1000 × price`
- 单位链：MWh → kWh（×1000）→ 元（× 元/kWh）
- 输出：元/日；周期收益 = 日收益 × horizon_days
- 边界：price ∈ [0.05, 2.0] 元/kWh（校验强制）

### 5. 清洗成本
- 输入：`cleaning_cost`（元/次，用户可调，config）
- 输出：元
- 边界：≥ 0（校验强制）

### 6. 停机损失
- 公式：`downtime_loss = theory_mwh_day ÷ 24 × downtime_hours × price × 1000`
- 单位链：MWh/日 → MWh/h（÷24）→ × 停机小时 → kWh（×1000）→ 元
- 边界：downtime_hours ∈ [0, 48]

### 7. 投资回收期
- 公式：`payback = cleaning_cost ÷ daily_revenue`（天）
- 边界：daily_revenue ≤ 0 时返回 None（前端显示 "--"）

### 8. 降雨阻塞
- 计算：`rain_next48 = sum(days[:2].rain)`（mm）
- 阻塞条件：`rain_next48 ≥ rain_limit_mm（1.0 mm）`
- 边界：预报仅 1 天时只累加 1 天（48h 窗口不完整）——**已知限制**，当前 forecast_days=3 恒有 2 天，触发条件受 sanitize 保护（不足 2 天有效数据时该天已被剔除，全空则降级）

### 9. 风速安全判断
- 计算：`wind_max = max(days.wind)`（m/s，源头参数保证）
- 阻塞条件：`wind_max ≥ wind_limit_ms（12 m/s）`
- 边界测试（本次新增）：11.9 m/s → 不阻塞（clean）；12.0 m/s → 阻塞（defer）
- 配置说明：`pv_config.json` 中 `wind_limit_ms` 字段名即单位，sources 已注明"清洗作业安全风速阈值"

## 四、行为变更说明（有意变更，非破坏）

| 旧行为 | 新行为 | 理由 |
|---|---|---|
| wind/rain 缺失或负值 → 归 0 保留该天 | **剔除该天** | 缺失数据不得参与正式计算；归 0 会误判"无风无雨可作业" |
| dust 缺失 → 填 fallback 值 80 且 quality=live | dust=None | 模拟值不得混入真实数据 |
| 辐照原始 MJ 直接使用 | ÷3.6 一次后使用 | 单位正确性 |
| 风速原始 km/h 直接使用 | 请求参数源头 m/s | 单位正确性 |

## 五、测试记录（真实执行）

执行命令：
```bash
cd /workspace/pv-agent/backend && python -m pytest tests -q
```

执行结果：**66 passed, 0 failed, 0 skipped**（2.38s）

新增测试（17 项）：
- `test_units.py`（12 项）：18 MJ→5 kWh、36 km/h→10 m/s、0/空值/负数/非数字/布尔拒绝、范围守卫、单位缺失拒绝、管道不重复转换、二次转换显式不等
- `test_weather.py`（+3 项）：全有效才保留、wind/rain 缺失剔除、`_daily_to_raw_days` 单位转换与缺字段
- `test_pv_model.py`（+2 项）：风速 11.9/12.0 m/s 阈值边界

更新测试（2 项，匹配新正确行为）：
- `test_sanitize_days_keeps_valid_rows` → `test_sanitize_days_keeps_only_fully_valid_rows`
- `test_sanitize_days_rejects_invalid_irradiance`（口径不变，保留）

## 六、遗留事项（转入 P1/P2，不在本阶段）

- P1-5 Git 分叉同步（fetch + 对齐 + push，本阶段提交时一并处理）
- P1-7 MCP 静默吞异常、P1-8 结构化日志
- P2-9 uvicorn 绑定 127.0.0.1
- 已知限制：预报不足 2 天时 48h 降水窗口不完整（当前被 forecast_days=3 与剔除规则保护）