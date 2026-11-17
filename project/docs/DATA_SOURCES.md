# DATA_SOURCES · 官方公开数据源接入文档

日期：2026-11-15（V3.0 第三阶段）
原则：无企业真实电站数据时，只使用真实可追溯的公开数据；严格区分预报、历史、缓存、用户输入与模拟数据，绝不混淆。

---

## 一、统一数据记录结构（DataRecord）

每条数据必须携带以下元数据（`backend/data_sources/models.py`）：

| 字段 | 含义 | 取值 |
|---|---|---|
| source | 数据源名称 | open-meteo-forecast / open-meteo-air / pvgis / nasa-power / demo-builtin / fallback-builtin |
| data_type | 业务类型 | weather_forecast / air_quality_forecast / solar_resource_historical |
| data_kind | **数据性质** | forecast（预报）/ historical（历史）/ user_input（用户输入）/ simulation（模拟） |
| latitude / longitude | 经纬度 | 保留 4 位小数 |
| value | 数据值 | 结构随源而定 |
| unit | 单位 | 与 value 一一对应 |
| valid_time | 数据覆盖时间 | 如 "2026-11-15 ~ 2026-11-17" |
| fetched_at | 实际获取时间 | ISO8601 本地时区 |
| status | 状态 | ok / cached / error |
| is_simulated | 是否模拟 | demo 与 fallback 均为 true |
| is_cached | 是否缓存 | 命中缓存时 true，且 fetched_at 保留原始时间 |
| error_message | 失败原因 | 仅 status=error 时非空 |

## 二、数据源清单

### 1. Open-Meteo Forecast（天气预报）

- **官方地址**：https://open-meteo.com/en/docs
- **接口**：`https://api.open-meteo.com/v1/forecast`
- **data_type / data_kind**：`weather_forecast` / **forecast（预报，非实测）**
- **使用字段与单位**：

| 字段 | 接口原始单位 | 项目内单位 | 转换 |
|---|---|---|---|
| shortwave_radiation_sum | MJ/m² | kWh/m² | **÷3.6，在 `_daily_to_raw_days` 内唯一一次转换** |
| precipitation_sum | mm | mm | 不转换 |
| wind_speed_10m_max | 请求参数 `wind_speed_unit=ms` 声明 | m/s | 源头统一，不做二次换算 |
| cloud_cover_mean | % | % | 不转换 |
| temperature_2m_max / min | °C | °C | 仅展示，不参与决策计算 |

- **时间尺度**：未来 3 天，逐日
- **接口限制**：免费、无需 API Key；非商业用途开放（官方条款）
- **实际验证状态**：✅ **2026-11-15 22:36 实测 HTTP 200**（1.8s）。真实响应摘要：11-15 辐照 9.27 MJ/m²（转换后 2.57 kWh/m²）、风速 2.33 m/s、最高温 5.3 °C；11-16/17 辐照 4.77/9.33 MJ/m²

### 2. Open-Meteo Air Quality（空气质量预报）

- **官方地址**：https://open-meteo.com/en/docs/air-quality-api
- **接口**：`https://air-quality-api.open-meteo.com/v1/air-quality`
- **data_type / data_kind**：`air_quality_forecast` / **forecast（预报，非地面监测站实测数据）**
- **使用字段与单位**：pm10 / pm2_5 / dust，均为 **μg/m³**，取 48 小时预报均值
- **时间尺度**：未来 48 小时，逐小时
- **接口限制**：免费、无需 Key
- **实际验证状态**：✅ **2026-11-15 22:36 实测 HTTP 200**（3.4s）。真实响应摘要：PM10 均值 66.6 μg/m³、PM2.5 24.4 μg/m³、dust 75.4 μg/m³
- **注意**：dust 字段为接口提供的沙尘预报参数；缺失时置 None，不填默认值

### 3. PVGIS（太阳能资源，历史气候）

- **官方地址**：https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis_en
- **接口**：`https://re.jrc.ec.europa.eu/api/v5_3/PVcalc`
- **data_type / data_kind**：`solar_resource_historical` / **historical（ERA5 2005–2023 历史气候均值，非实时数据）**
- **使用字段与单位**：E_d（kWh/kWp，当月日均发电量）；radiation_db / year_min / year_max 用于溯源标注
- **时间尺度**：月均值（基于 19 年历史再分析）
- **缓存**：6 小时内存缓存（`DS_CACHE_TTL` 可配）；命中时 `is_cached=true` 且保留原始 `fetched_at`
- **接口限制**：免费、无需注册；官方建议非高频调用（缓存已缓解）
- **实际验证状态**：✅ **2026-11-15 22:36 实测 HTTP 200**（1.1s）。真实响应摘要：PVGIS-ERA5（2005–2023），11 月 E_d = 3.79 kWh/kWp
- **口径说明**：PVGIS 回答"这个月通常能发多少电"（历史气候），天气预报回答"未来三天能不能洗"——两者不混用

### 4. NASA POWER（可选历史补充源）

- **官方地址**：https://power.larc.nasa.gov/
- **接口**：`https://power.larc.nasa.gov/api/temporal/daily/point`
- **data_type / data_kind**：`solar_resource_historical` / **historical（再分析，非实时）**
- **使用字段与单位**：ALLSKY_SFC_SW_DWN（**kWh/m²/day，接口原生单位，无需转换**）、T2M_MAX / T2M_MIN（°C）
- **时间尺度**：逐日历史（参数 start/end，格式 YYYYMMDD）
- **接口限制**：免费、无需 Key；响应较慢（实测 2.4s）
- **启用方式**：默认**关闭**，设置 `NASA_POWER_ENABLED=1` 启用（避免无谓的外部依赖）
- **实际验证状态**：✅ **2026-11-15 22:33 实测 HTTP 200**（2.4s）。真实响应摘要：11-01~11-08 辐照 2.36–3.13 kWh/m²/day，与 PVGIS 11 月 E_d=3.79 同量级（交叉验证一致）
- **用途**：与 PVGIS 交叉校验历史辐照口径

## 三、数据真实性规则落实情况

| 规则 | 落实方式 |
|---|---|
| 只有真实调用成功才标记成功 | status=ok 仅在接口 200 且数据通过校验后 |
| 缓存显示缓存状态与原始时间 | is_cached=true + fetched_at 保留原始值（有测试锁定） |
| 模拟数据标记 simulation | demo/fallback 均生成 simulation_record，is_simulated=true |
| 用户输入标记 user_input | 电站参数（装机/电价/成本/天数）为 user_input，见 pv_config 与请求模型 |
| 天气预报不称实时监测 | data_kind=forecast，data_type=weather_forecast，文档与前端均标注"预报" |
| 历史数据不称当前数据 | PVGIS/NASA 标注 historical + valid_time 注明"2005–2023 历史均值" |
| 接口失败明确显示失败 | data_sources 层返回 status=error + error_message，**不注入模拟数据**；聚合层降级时追加 simulation 记录显式标注 |
| 不硬编码 API Key | 四个源全部免 Key；LLM 密钥仅存于 .env（已 gitignore） |

## 四、容错与质量机制（backend/data_sources/base.py）

- **超时**：`DS_TIMEOUT`（默认 10s，PVGIS 12s，NASA 15s）
- **重试**：`DS_RETRIES`（默认 2 次，间隔递增 0.6s/1.2s）
- **缓存**：`DS_CACHE_TTL`（默认 21600s=6h），键含经纬度与参数；过期自动失效
- **完整性校验**：辐照 [0,12] kWh/m²、风速 [0,60] m/s、降水 [0,500] mm、温度 [-60,60] °C；决策必需字段（辐照/风速/降水）缺失即剔除该天
- **经纬度校验**：[-90,90] / [-180,180]，非法直接 error
- **错误日志**：每次请求（成功/失败）写入内存健康表，`GET /api/data-sources/health` 可查
- **部分降级**：单源失败不影响其他源；聚合层 quality 分级 live-good / live-degraded / fallback

## 五、测试与验证声明

**Mock 测试（12 项，`tests/test_data_sources.py`）**：覆盖正常、超时、异常、空数据、缓存命中（保留原始时间）、缓存过期、经纬度非法、NASA 未启用、健康状态记录（成功/失败）。**Mock 测试仅证明程序处理逻辑正确，不代表真实 API 连通。**

**真实调用验证（2026-11-15 22:36，本环境联网实测）**：

```
整体质量: live-good | 拉取时间: 2026-11-15T22:36:43+08:00
  open-meteo-forecast    kind=forecast   status=ok   → 辐照 2.57 kWh/m² · 风 2.3 m/s · 温 5.3 °C
  open-meteo-air         kind=forecast   status=ok   → PM10 66.6 μg/m³ · dust 75.4 · PM2.5 24.4
  pvgis                  kind=historical status=ok   → E_d 3.79 kWh/kWp（ERA5 2005-2023）
```

**待验证项**：NASA POWER 生产链路未启用（默认关闭，仅完成接口实测与适配）；长时间运行的缓存过期行为仅经单元测试验证。

## 六、环境变量配置（.env.example）

```
DS_TIMEOUT=10          # 数据源请求超时（秒）
DS_RETRIES=2           # 失败重试次数
DS_CACHE_TTL=21600     # 缓存有效期（秒，默认 6 小时）
NASA_POWER_ENABLED=0   # NASA POWER 可选源开关（1=启用）
```

全部数据源免 API Key；LLM 密钥（LLM_API_KEY）仅存于 .env，已列入 .gitignore，不进入 Git 与交付包。