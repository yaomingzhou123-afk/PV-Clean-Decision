const pptxgen = require('pptxgenjs');
const path = require('path');

const pres = new pptxgen();
pres.layout = 'LAYOUT_WIDE'; // 13.3 x 7.5 inches

const C = {
  bgDark: '0F1B33', bgLight: 'FFFFFF', primary: '1B3A5C', tech: '2E86DE',
  light: 'EBF3FB', gold: 'F5B544', text: '1A1A2E', white: 'FFFFFF',
  gray: '6B7280', green: '27AE60', red: 'E74C3C', mid: '3E5C8A',
};
const SHOTS = '/workspace/PV-Clean-Decision/presentation/screenshots';
const W = 13.33, H = 7.5;

function header(s, title, sub) {
  s.background = { color: C.bgLight };
  s.addText(title, { x: 0.6, y: 0.35, w: 10, h: 0.7, fontSize: 30, bold: true, color: C.primary, fontFace: 'Cambria', margin: 0 });
  if (sub) s.addText(sub, { x: 0.6, y: 1.0, w: 11, h: 0.4, fontSize: 13, color: C.gray, fontFace: 'Calibri', margin: 0 });
}
function pageNum(s, n) {
  s.addText(String(n), { x: W - 0.8, y: H - 0.5, w: 0.4, h: 0.3, fontSize: 10, color: C.gray, align: 'right', margin: 0 });
}
function card(s, x, y, w, h, fill, line) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h, fill: { color: fill || C.light }, line: { color: line || 'D5E3F0', width: 1 }, rectRadius: 0.08 });
}
function chip(s, x, y, w, text, color) {
  s.addShape(pres.ShapeType.roundRect, { x, y, w, h: 0.32, fill: { color: color || C.tech }, line: { type: 'none' }, rectRadius: 0.16 });
  s.addText(text, { x, y, w, h: 0.32, fontSize: 10, bold: true, color: C.white, align: 'center', valign: 'middle', margin: 0 });
}

// ============ P1 封面 ============
let s = pres.addSlide();
s.background = { color: C.bgDark };
s.addShape(pres.ShapeType.ellipse, { x: 10.8, y: -1.2, w: 4.5, h: 4.5, fill: { color: '1A2C4F' }, line: { type: 'none' } });
s.addShape(pres.ShapeType.ellipse, { x: 11.5, y: -0.5, w: 3.0, h: 3.0, fill: { color: '23386B' }, line: { type: 'none' } });
s.addShape(pres.ShapeType.ellipse, { x: -1.5, y: 5.5, w: 4, h: 4, fill: { color: '16263F' }, line: { type: 'none' } });
s.addText('☀', { x: 11.6, y: 0.1, w: 1.6, h: 1.6, fontSize: 72, color: C.gold, align: 'center', margin: 0 });
s.addText('疆光 · PV-Clean-Decision', { x: 0.8, y: 1.9, w: 11.5, h: 1.0, fontSize: 44, bold: true, color: C.white, fontFace: 'Cambria', margin: 0 });
s.addText('基于多 Agent 协作的光伏电站沙尘清洗决策智能体', { x: 0.8, y: 3.0, w: 11, h: 0.6, fontSize: 20, color: C.gold, fontFace: 'Calibri', margin: 0 });
s.addText('七个规则 Agent 真实执行 · MCP 标准协议 · 全链路数据可信标注 · 206 项测试全绿', { x: 0.8, y: 3.8, w: 11, h: 0.5, fontSize: 14, color: 'AAB8D0', margin: 0 });
s.addShape(pres.ShapeType.line, { x: 0.8, y: 4.6, w: 4, h: 0, line: { color: C.gold, width: 2 } });
s.addText('2026 华为开发者大赛 · 智能体创新赛', { x: 0.8, y: 4.9, w: 6, h: 0.4, fontSize: 14, color: '8FA3C0', margin: 0 });
s.addText('技术栈：Python 3.12 / FastAPI / MCP JSON-RPC / 原生前端', { x: 0.8, y: 5.4, w: 8, h: 0.4, fontSize: 12, color: '6B7A99', margin: 0 });

// ============ P2 行业背景与痛点 ============
s = pres.addSlide();
header(s, '行业背景与痛点', '新疆光伏基地的清洗决策困境');
pageNum(s, 2);
const pains = [
  { icon: '🏜', t: '沙尘污染严重', d: '新疆地处沙尘频发区，PM10 常年高于 80 μg/m³，光伏组件积灰导致发电损失可达 15%（模型上限）。' },
  { icon: '💰', t: '清洗成本高', d: '20MW 电站单次全站清洗约 4,000 元（人工+用水+设备），盲目清洗造成资源浪费。' },
  { icon: '❓', t: '决策靠经验', d: '何时洗、洗多少、值不值——目前主要依赖人工经验判断，缺乏可解释、可追溯的量化决策工具。' },
];
pains.forEach((p, i) => {
  const x = 0.7 + i * 4.1;
  card(s, x, 1.8, 3.8, 3.6, C.light);
  s.addShape(pres.ShapeType.ellipse, { x: x + 0.3, y: 2.1, w: 0.7, h: 0.7, fill: { color: C.tech }, line: { type: 'none' } });
  s.addText(p.icon, { x: x + 0.3, y: 2.1, w: 0.7, h: 0.7, fontSize: 28, align: 'center', valign: 'middle', margin: 0 });
  s.addText(p.t, { x: x + 0.3, y: 3.0, w: 3.2, h: 0.5, fontSize: 18, bold: true, color: C.primary, margin: 0 });
  s.addText(p.d, { x: x + 0.3, y: 3.5, w: 3.2, h: 1.7, fontSize: 12, color: C.text, margin: 0, lineSpacing: 18 });
});
s.addText('核心问题：清洗收益 vs 清洗成本 vs 作业安全，三重约束下的最优决策', { x: 0.7, y: 5.8, w: 12, h: 0.5, fontSize: 15, bold: true, color: C.tech, align: 'center', margin: 0 });

// ============ P3 项目解决方案 ============
s = pres.addSlide();
header(s, '项目解决方案', '一套可解释、可追溯、可现场演示的清洗决策智能体');
pageNum(s, 3);
const sols = [
  { n: '01', t: '七 Agent 协作决策', d: '气象/污损/发电/经济/安全/审查/决策七个 Agent 基于同一数据快照独立分析，Safety 可否决、Critic 可驳回、Decision 输出最终结论。' },
  { n: '02', t: 'MCP 标准工具层', d: 'JSON-RPC 2024-11-05 真实协议，get_site_data / search_knowledge / calc_economics 三个工具，参数校验 + 失败降级。' },
  { n: '03', t: '全链路数据可信', d: '每条数据标注来源/获取时间/覆盖时间/是否模拟/是否缓存；live 模式下关键源降级即拒绝决策（insufficient_data）。' },
  { n: '04', t: '模拟实验室', d: '17 个参数实时重算、三种清洗策略对照（固定周期/污损阈值/天气经济联合）、9 组单因素影响曲线。' },
];
sols.forEach((p, i) => {
  const x = 0.7 + (i % 2) * 6.2, y = 1.7 + Math.floor(i / 2) * 2.5;
  card(s, x, y, 5.8, 2.2, i % 2 === 0 ? C.light : 'F8FBFE');
  s.addText(p.n, { x: x + 0.25, y: y + 0.2, w: 0.9, h: 0.7, fontSize: 32, bold: true, color: C.gold, fontFace: 'Cambria', margin: 0 });
  s.addText(p.t, { x: x + 1.2, y: y + 0.2, w: 4.3, h: 0.45, fontSize: 17, bold: true, color: C.primary, margin: 0 });
  s.addText(p.d, { x: x + 1.2, y: y + 0.7, w: 4.3, h: 1.3, fontSize: 11.5, color: C.text, margin: 0, lineSpacing: 16 });
});

// ============ P4 系统技术架构 ============
s = pres.addSlide();
header(s, '系统技术架构', '四层架构：数据源 → MCP 工具层 → 七 Agent 决策 → 前端驾驶舱');
pageNum(s, 4);
const layers = [
  { y: 1.55, h: 1.05, label: '前端展示层', color: C.light, items: ['决策驾驶舱（13 项信息一屏展示）', 'Agent 问答（Function Calling）', '模拟实验室（17 参数实时重算）', '数据质量面板（来源/时间/模拟/缺失/错误）'] },
  { y: 2.85, h: 1.05, label: 'Agent 决策层', color: 'E8F4FD', items: ['七 Agent 顺序执行（agent_team.py）', 'Safety 三条件否决（数据>天气>间隔）', 'Critic 四类规则审查 + LLM 可选增强', 'Decision 保守序仲裁 + decision_trace'] },
  { y: 4.15, h: 1.05, label: 'MCP 工具层', color: 'F0F7FE', items: ['JSON-RPC 2024-11-05（stdio 子进程）', 'get_site_data：拉取站点数据', 'search_knowledge：RAG 检索（36 条知识库）', 'calc_economics：确定性经济计算'] },
  { y: 5.45, h: 1.05, label: '公开数据源', color: 'F5F9FD', items: ['Open-Meteo Forecast（3 天天气预报）', 'Open-Meteo Air Quality（PM10/PM2.5/沙尘）', 'PVGIS（ERA5 2005-2023 理论发电量）', '全部免 API Key · 失败自动降级标注'] },
];
layers.forEach((l, i) => {
  s.addShape(pres.ShapeType.roundRect, { x: 0.7, y: l.y, w: 11.9, h: l.h, fill: { color: l.color }, line: { color: 'C8D9EA', width: 1 }, rectRadius: 0.06 });
  s.addText(l.label, { x: 0.95, y: l.y + 0.12, w: 1.8, h: l.h - 0.24, fontSize: 14, bold: true, color: C.primary, valign: 'middle', margin: 0 });
  l.items.forEach((it, j) => {
    s.addText('• ' + it, { x: 2.9 + j * 2.5, y: l.y + 0.12, w: 2.45, h: l.h - 0.24, fontSize: 10, color: C.text, valign: 'middle', margin: 0, lineSpacing: 13 });
  });
  if (i < 3) s.addText('▲', { x: 6.5, y: l.y + l.h - 0.06, w: 0.3, h: 0.22, fontSize: 10, color: C.tech, align: 'center', margin: 0 });
});
s.addText('工程保障：206 项 pytest 全绿 · GitHub Actions CI · 请求日志 · 统一错误响应 · 13 个 REST 接口 + 2 个流式接口', { x: 0.7, y: 6.7, w: 12, h: 0.4, fontSize: 11, color: C.gray, margin: 0 });

// ============ P5 多 Agent 协作 ============
s = pres.addSlide();
header(s, '多 Agent 协作机制', '七个 Agent 真实执行，非展示层装饰');
pageNum(s, 5);
const agents = [
  { id: 'Weather', c: C.tech, d: '天气窗口判断' }, { id: 'Soiling', c: '8E44AD', d: '污损风险估算' },
  { id: 'PV Performance', c: 'E67E22', d: '发电损失分析' }, { id: 'Economic', c: '27AE60', d: '清洗经济性' },
  { id: 'Safety', c: 'E74C3C', d: '安全否决（可一票否决）' }, { id: 'Critic', c: 'F39C12', d: '审查驳回（可阻止清洗）' },
  { id: 'Decision', c: '1B3A5C', d: '最终仲裁' },
];
agents.forEach((a, i) => {
  const x = 0.7 + i * 1.75;
  s.addShape(pres.ShapeType.roundRect, { x, y: 1.7, w: 1.6, h: 1.5, fill: { color: C.white }, line: { color: a.c, width: 2 }, rectRadius: 0.08 });
  s.addShape(pres.ShapeType.ellipse, { x: x + 0.55, y: 1.82, w: 0.5, h: 0.5, fill: { color: a.c }, line: { type: 'none' } });
  s.addText(String(i + 1), { x: x + 0.55, y: 1.82, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: C.white, align: 'center', valign: 'middle', margin: 0 });
  s.addText(a.id, { x: x + 0.05, y: 2.4, w: 1.5, h: 0.35, fontSize: 10, bold: true, color: C.primary, align: 'center', margin: 0 });
  s.addText(a.d, { x: x + 0.05, y: 2.72, w: 1.5, h: 0.4, fontSize: 8.5, color: C.gray, align: 'center', margin: 0 });
});
const mechs = [
  { t: 'Safety 否决机制', d: '三条件否决，优先级：数据质量 > 天气安全 > 最小间隔。否决后 Decision 必须遵守保守序（clean < hold < defer < insufficient_data），不得给出比规则更激进的决策。', c: C.red },
  { t: 'Critic 审查机制', d: '四类确定性规则审查：① 净收益计算复核（容差 2 元）② 结论矛盾检测 ③ 模拟数据误标检测 ④ 单位抽查。发现高危问题输出 reject，Decision 收到 reject 后阻止 clean 决策。', c: 'F39C12' },
  { t: 'LLM 可选增强', d: 'Critic 支持将七 Agent 结论交 LLM 补充审查（限 1 次调用，输出必须通过 JSON 结构校验）。LLM 不可用时规则审查独立完成，决策链路不受影响。', c: C.tech },
];
mechs.forEach((m, i) => {
  const x = 0.7 + i * 4.1;
  card(s, x, 3.6, 3.8, 2.9, C.white, m.c);
  s.addText(m.t, { x: x + 0.25, y: 3.8, w: 3.3, h: 0.4, fontSize: 15, bold: true, color: m.c, margin: 0 });
  s.addText(m.d, { x: x + 0.25, y: 4.25, w: 3.3, h: 2.1, fontSize: 11, color: C.text, margin: 0, lineSpacing: 15 });
});
s.addText('每个 Agent 输出统一结构：结论 + 证据表 + 数据源 + 假设 + 不确定性 + 置信度（标注 heuristic 启发式评分，非概率）', { x: 0.7, y: 6.75, w: 12, h: 0.4, fontSize: 11, color: C.gray, margin: 0 });

// ============ P6 核心算法 ============
s = pres.addSlide();
header(s, '核心算法', '确定性污损-经济模型，参数来源全部可追溯');
pageNum(s, 6);
card(s, 0.7, 1.7, 5.9, 2.6, C.light);
s.addText('积灰估算模型（线性累积）', { x: 1.0, y: 1.9, w: 5.3, h: 0.4, fontSize: 16, bold: true, color: C.primary, margin: 0 });
s.addText('日污损速率 = 基础速率(0.4%/天)\n         + max(0, PM10 − 80) × 0.00035\n         + max(0, PM2.5 − 35) × 0.00005（演示系数）', { x: 1.0, y: 2.4, w: 5.3, h: 1.0, fontSize: 12, color: C.text, fontFace: 'Courier New', margin: 0, lineSpacing: 16 });
s.addText('污损损失率 = min(15% 上限, 日速率 × 天数 × 倾角因子)\n输出标注 method=model_estimate（非传感器实测）', { x: 1.0, y: 3.5, w: 5.3, h: 0.7, fontSize: 11, color: C.gray, margin: 0, lineSpacing: 15 });
card(s, 6.9, 1.7, 5.7, 2.6, 'F8FBFE');
s.addText('清洗经济性公式', { x: 7.2, y: 1.9, w: 5.1, h: 0.4, fontSize: 16, bold: true, color: C.primary, margin: 0 });
s.addText('有效可恢复损失 = 污损率 × 恢复效率(0.95)\n                 × (1 − 自然清洁折减)\n日增量收益 = 理论日发电量 × 有效损失 × 1000 × 电价\n净收益 = 日增量收益 × 评估周期 − 清洗成本 − 停机损失', { x: 7.2, y: 2.4, w: 5.1, h: 1.3, fontSize: 11.5, color: C.text, fontFace: 'Courier New', margin: 0, lineSpacing: 15 });
s.addText('停机损失 = 理论日发电量 ÷ 24 × 停机小时 × 电价 × 1000', { x: 7.2, y: 3.75, w: 5.1, h: 0.35, fontSize: 11, color: C.gray, fontFace: 'Courier New', margin: 0 });
card(s, 0.7, 4.6, 12.0, 2.2, C.white, 'C8D9EA');
s.addText('单因素确定性敏感性分析（12 场景）', { x: 1.0, y: 4.8, w: 6, h: 0.4, fontSize: 15, bold: true, color: C.primary, margin: 0 });
s.addText('电价 ±20% · 清洗成本 ±20% · 污损速率 ±20% · 恢复效率 1.00/0.90 · 发电水平 ±20%（PVGIS 模式扰动 E_d） · 降雨自然清洁 0/0.6', { x: 1.0, y: 5.25, w: 11.3, h: 0.4, fontSize: 12, color: C.text, margin: 0 });
s.addText('每次仅改变一个参数并完整重算净收益与决策；非蒙特卡洛，无概率分布假设，不输出编造的置信概率。', { x: 1.0, y: 5.7, w: 11.3, h: 0.4, fontSize: 11, color: C.gray, margin: 0 });
s.addText('参数来源：基础速率/PM10 系数来自公开研究趋势标定（待实测修正）；电价为新疆燃煤标杆政策值；安全阈值由用户配置（非行业统一标准）。', { x: 1.0, y: 6.15, w: 11.3, h: 0.5, fontSize: 10, color: C.gray, margin: 0 });

// ============ P7 清洗经济性决策 ============
s = pres.addSlide();
header(s, '清洗经济性决策', '四种决策 · 保守优先 · 全程可追溯');
pageNum(s, 7);
const flows = [
  { t: '建议清洗 clean', c: C.green, d: '天气窗口满足 + 间隔满足 + 净收益为正' },
  { t: '建议延后 defer', c: C.gold, d: '天气阻塞（降雨/大风超阈值）' },
  { t: '暂不清洗 hold', c: C.gray, d: '间隔不足或净收益为负' },
  { t: '数据不足 insufficient_data', c: C.red, d: '关键源缺失或降级，拒绝基于模拟数据决策' },
];
flows.forEach((f, i) => {
  const x = 0.7 + i * 3.1;
  s.addShape(pres.ShapeType.roundRect, { x, y: 1.7, w: 2.9, h: 1.3, fill: { color: C.white }, line: { color: f.c, width: 2 }, rectRadius: 0.08 });
  s.addText(f.t, { x: x + 0.15, y: 1.82, w: 2.6, h: 0.4, fontSize: 13, bold: true, color: f.c, margin: 0 });
  s.addText(f.d, { x: x + 0.15, y: 2.22, w: 2.6, h: 0.7, fontSize: 10, color: C.text, margin: 0, lineSpacing: 13 });
});
s.addText('决策优先级：数据不足 > 天气安全 > 最小间隔 > 经济性（保守序，Safety/Critic 可否决）', { x: 0.7, y: 3.2, w: 12, h: 0.4, fontSize: 12, bold: true, color: C.tech, margin: 0 });
const stats = [
  { v: '39,478', u: '元', l: 'demo 场景净收益' },
  { v: '1.2', u: '天', l: '投资回收期' },
  { v: '15.0', u: '%', l: '估算污损损失' },
  { v: '95.1', u: 'MWh', l: '理论日发电量' },
];
stats.forEach((st, i) => {
  const x = 0.7 + i * 3.1;
  card(s, x, 3.9, 2.9, 2.0, C.light);
  s.addText(st.v, { x: x + 0.15, y: 4.1, w: 2.6, h: 0.9, fontSize: 40, bold: true, color: C.primary, fontFace: 'Cambria', align: 'center', margin: 0 });
  s.addText(st.u, { x: x + 0.15, y: 4.95, w: 2.6, h: 0.35, fontSize: 14, color: C.tech, align: 'center', margin: 0 });
  s.addText(st.l, { x: x + 0.15, y: 5.3, w: 2.6, h: 0.35, fontSize: 11, color: C.gray, align: 'center', margin: 0 });
});
s.addText('实测数据：20MW / 距上次清洗 20 天 / PM10 135 μg/m³ / 电价 0.25 元/kWh / 清洗成本 4,000 元（demo 演示样例，非真实电站）', { x: 0.7, y: 6.2, w: 12, h: 0.4, fontSize: 10, color: C.gray, margin: 0 });

// ============ P8 数据来源与可信度 ============
s = pres.addSlide();
header(s, '数据来源与可信度', '三个公开数据源 · 全链路诚实标注 · 不伪装成功');
pageNum(s, 8);
const dsrcs = [
  { t: 'Open-Meteo Forecast', d: '3 天天气预报：辐照/降水/风速/云量/温度。免 API Key，失败自动降级为内置样例并标注 is_simulated=true。', tag: '天气预报' },
  { t: 'Open-Meteo Air Quality', d: 'PM10 / PM2.5 / 沙尘浓度预报。与污损模型直接关联，PM10 超基准 80 μg/m³ 时线性增加日污损速率。', tag: '空气质量' },
  { t: 'PVGIS（欧盟 JRC）', d: 'ERA5 2005-2023 历史气候均值，提供月均日发电量 E_d（kWh/kWp）。缓存 6 小时，标注 data_kind=historical（非实时）。', tag: '理论发电量' },
];
dsrcs.forEach((d, i) => {
  const x = 0.7 + i * 4.1;
  card(s, x, 1.7, 3.8, 2.6, C.light);
  chip(s, x + 0.25, 1.9, 1.4, d.tag, C.tech);
  s.addText(d.t, { x: x + 0.25, y: 2.35, w: 3.3, h: 0.4, fontSize: 15, bold: true, color: C.primary, margin: 0 });
  s.addText(d.d, { x: x + 0.25, y: 2.8, w: 3.3, h: 1.4, fontSize: 11, color: C.text, margin: 0, lineSpacing: 15 });
});
const trust = [
  '每条数据记录：source / data_kind / fetched_at / valid_time / unit / is_cached / is_simulated / status / error_message',
  '数据质量面板：前端逐条展示以上 9 个字段，模拟数据金色标注"模拟"，失败红色标注原因',
  'live 模式下预报或空气质量任一降级为 fallback → 直接输出 insufficient_data，不用模拟数据给真实决策',
  '导出报告：数据来源按实际记录动态生成（demo 报告显示"demo-builtin（模拟）"而非硬编码 Open-Meteo）',
];
s.addText('可信度保障机制', { x: 0.7, y: 4.6, w: 4, h: 0.4, fontSize: 16, bold: true, color: C.primary, margin: 0 });
trust.forEach((t, i) => {
  s.addText('✓ ' + t, { x: 0.7, y: 5.05 + i * 0.5, w: 12, h: 0.45, fontSize: 11.5, color: C.text, margin: 0 });
});

// ============ P9 真实系统截图 ============
s = pres.addSlide();
header(s, '真实系统截图', '决策驾驶舱 · 七 Agent 时间线 · 模拟实验室');
pageNum(s, 9);
s.addImage({ path: path.join(SHOTS, '02_decision_full.png'), x: 0.5, y: 1.6, w: 7.6, h: 4.28, sizing: { type: 'contain', w: 7.6, h: 4.28 } });
s.addText('▲ 决策驾驶舱：七 Agent 逐个执行，KPI / 决策结论 / 证据 / 数据质量一屏展示', { x: 0.5, y: 5.95, w: 7.6, h: 0.35, fontSize: 10, color: C.gray, margin: 0 });
s.addImage({ path: path.join(SHOTS, '05_simulation_lab.png'), x: 8.3, y: 1.6, w: 4.6, h: 2.59, sizing: { type: 'contain', w: 4.6, h: 2.59 } });
s.addText('▲ 模拟实验室', { x: 8.3, y: 4.25, w: 4.6, h: 0.3, fontSize: 10, color: C.gray, margin: 0 });
s.addImage({ path: path.join(SHOTS, '03_agent_timeline.png'), x: 8.3, y: 4.6, w: 4.6, h: 1.9, sizing: { type: 'contain', w: 4.6, h: 1.9 } });
s.addText('▲ Agent 时间线', { x: 8.3, y: 6.5, w: 4.6, h: 0.3, fontSize: 10, color: C.gray, margin: 0 });

// ============ P10 三个验证场景 ============
s = pres.addSlide();
header(s, '三个实际运行验证场景', '高积灰建议清洗 · 降雨暂缓 · 数据不足拒绝决策');
pageNum(s, 10);
const scenes = [
  { t: '场景 A · 高积灰', c: C.green, img: '02_decision_full.png', rows: [['决策', '建议清洗 clean'], ['净收益', '39,478 元'], ['回本', '1.2 天'], ['污损', '15.0%（模型估算）'], ['窗口', '演示 D2（辐照最高日）']] },
  { t: '场景 B · 降雨暂缓', c: C.gold, img: null, rows: [['决策', '建议延后 defer'], ['原因', '预计降雨 8mm ≥ 阈值 1mm'], ['污损', '15.0%（仍高）'], ['Safety', 'weather 否决生效'], ['处理', '等待安全窗口后复评']] },
  { t: '场景 C · 数据不足', c: C.red, img: null, rows: [['决策', '数据不足 insufficient_data'], ['触发', '断网 + live 模式'], ['Agent', '0 个执行（提前短路）'], ['页面', '显示"--"而非 0'], ['原则', '不用模拟数据给真实决策']] },
];
scenes.forEach((sc, i) => {
  const x = 0.7 + i * 4.1;
  card(s, x, 1.7, 3.8, 4.9, C.white, sc.c);
  s.addShape(pres.ShapeType.roundRect, { x: x + 0.2, y: 1.9, w: 3.4, h: 0.5, fill: { color: sc.c }, line: { type: 'none' }, rectRadius: 0.1 });
  s.addText(sc.t, { x: x + 0.2, y: 1.9, w: 3.4, h: 0.5, fontSize: 14, bold: true, color: C.white, align: 'center', valign: 'middle', margin: 0 });
  sc.rows.forEach((r, j) => {
    s.addText(r[0], { x: x + 0.3, y: 2.6 + j * 0.62, w: 1.1, h: 0.5, fontSize: 11, bold: true, color: C.gray, margin: 0 });
    s.addText(r[1], { x: x + 1.45, y: 2.6 + j * 0.62, w: 2.2, h: 0.5, fontSize: 11, color: C.text, margin: 0 });
  });
});
s.addText('三个场景均为实际启动服务后运行的真实结果，非虚构数据。场景 B/C 通过模拟实验室参数和断网环境构造。', { x: 0.7, y: 6.8, w: 12, h: 0.35, fontSize: 10, color: C.gray, margin: 0 });

// ============ P11 项目创新点 ============
s = pres.addSlide();
header(s, '项目创新点', '五个可验证的差异化亮点');
pageNum(s, 11);
const inns = [
  { icon: '🤖', t: '七 Agent 真实协作 + 双否决', d: 'Safety 三条件否决 + Critic 四类审查驳回，Decision 遵守保守序。不是六个 Agent 各说各话，而是有否决权、有审查、有仲裁的完整治理链。' },
  { icon: '🔌', t: 'MCP 标准协议真实实现', d: 'JSON-RPC 2024-11-05 stdio 子进程，参数校验（-32602）、读超时、幂等关闭、失败降级直连。不是工具名展示层。' },
  { icon: '🔍', t: '全链路数据可信标注', d: '每条数据 9 个元数据字段；live 关键源降级即 insufficient_data；报告来源动态生成。不把模拟数据包装成真实数据。' },
  { icon: '🧪', t: '模拟实验室三策略对照', d: '17 参数实时重算（非前端改字），固定周期/污损阈值/天气经济联合三策略同一评价周期对比，9 组影响曲线由实际重算生成。' },
  { icon: '🛡', t: '答辩级稳定性修复', d: '10 项 P0 修复全部完成并配 28 项回归测试：数据不足短路七 Agent、Critic reject 阻止清洗、best_date 只从安全日中选等。' },
];
inns.forEach((p, i) => {
  const x = 0.7 + (i % 3) * 4.1, y = 1.7 + Math.floor(i / 3) * 2.6;
  card(s, x, y, 3.8, 2.3, i % 2 === 0 ? C.light : 'F8FBFE');
  s.addText(p.icon, { x: x + 0.25, y: y + 0.15, w: 0.6, h: 0.6, fontSize: 26, margin: 0 });
  s.addText(p.t, { x: x + 0.9, y: y + 0.2, w: 2.7, h: 0.5, fontSize: 13, bold: true, color: C.primary, margin: 0 });
  s.addText(p.d, { x: x + 0.25, y: y + 0.75, w: 3.3, h: 1.4, fontSize: 10.5, color: C.text, margin: 0, lineSpacing: 14 });
});

// ============ P12 真实测试结果 ============
s = pres.addSlide();
header(s, '真实测试结果', '206 项 pytest 全绿 · GitHub Actions CI');
pageNum(s, 12);
s.addText('206', { x: 0.8, y: 1.8, w: 3.5, h: 1.5, fontSize: 90, bold: true, color: C.primary, fontFace: 'Cambria', margin: 0 });
s.addText('项测试全部通过', { x: 0.8, y: 3.3, w: 3.5, h: 0.5, fontSize: 18, color: C.tech, margin: 0 });
s.addText('python3 -m pytest backend/tests -q\n206 passed in 29.3s', { x: 0.8, y: 3.9, w: 3.8, h: 0.7, fontSize: 12, color: C.gray, fontFace: 'Courier New', margin: 0, lineSpacing: 16 });
const tcats = [
  ['积灰/经济/决策模型', '46 项', '公式、边界、四种决策、敏感性、PM2.5、override'],
  ['七 Agent 团队', '22 项', '执行顺序、结构校验、Safety 否决、Critic 检测/误报消除'],
  ['稳定性修复回归', '28 项', 'P0 全量 10 项修复的专项回归测试'],
  ['MCP 协议', '19 项', '工具定义一致性、参数校验、超时、泄漏、幂等关闭'],
  ['模拟实验室', '30 项', '17 参数逐个重算、负收益不清洗、安全不清洗、非法输入'],
  ['REST API 接口', '31 项', '13 个接口、统一错误格式、站点配置白名单'],
  ['数据源/单位/RAG', '30 项', 'DataRecord 元数据、单位转换、知识库检索'],
];
s.addText('测试覆盖', { x: 5.0, y: 1.7, w: 3, h: 0.4, fontSize: 16, bold: true, color: C.primary, margin: 0 });
tcats.forEach((t, i) => {
  const y = 2.2 + i * 0.62;
  s.addText(t[0], { x: 5.0, y, w: 2.8, h: 0.5, fontSize: 11.5, bold: true, color: C.text, margin: 0 });
  s.addText(t[1], { x: 7.9, y, w: 0.7, h: 0.5, fontSize: 11.5, bold: true, color: C.tech, margin: 0 });
  s.addText(t[2], { x: 8.7, y, w: 4.0, h: 0.5, fontSize: 9.5, color: C.gray, margin: 0 });
});
s.addText('CI：GitHub Actions（Python 3.10/3.11/3.12 矩阵测试 + 前端 JS 语法/HTML 结构检查）', { x: 0.7, y: 6.8, w: 12, h: 0.35, fontSize: 11, color: C.gray, margin: 0 });

// ============ P13 应用价值与落地前景 ============
s = pres.addSlide();
header(s, '应用价值与落地前景', '从比赛原型到工程落地的路径');
pageNum(s, 13);
card(s, 0.7, 1.7, 5.8, 4.8, C.light);
s.addText('应用价值', { x: 1.0, y: 1.9, w: 4, h: 0.4, fontSize: 16, bold: true, color: C.primary, margin: 0 });
const vals = [
  '可解释：每个决策附带理由链（decision_trace）、证据表和数据来源，不是黑盒',
  '可追溯：从 PM10 数据到净收益数字，每一步公式和参数来源可查',
  '可信任：模拟数据诚实标注，数据不足时拒绝决策而非编造结论',
  '可演示：断网/无 LLM Key 时自动降级为规则引擎，现场演示零风险',
];
vals.forEach((v, i) => s.addText('• ' + v, { x: 1.0, y: 2.4 + i * 0.75, w: 5.2, h: 0.7, fontSize: 12, color: C.text, margin: 0, lineSpacing: 16 }));
card(s, 6.9, 1.7, 5.7, 4.8, 'F8FBFE');
s.addText('落地路径', { x: 7.2, y: 1.9, w: 4, h: 0.4, fontSize: 16, bold: true, color: C.primary, margin: 0 });
const steps = [
  ['第一步', '接入电站 SCADA 实测发电量，替换 PVGIS 均值口径，校准污损模型参数'],
  ['第二步', '接入现场积灰传感器或无人机巡检数据，替换 PM10 代理估算'],
  ['第三步', '对接实际清洗工单与合同价格，替换示例成本假设'],
  ['第四步', '部署至电站运维平台，按方阵粒度输出分区清洗计划'],
];
steps.forEach((st, i) => {
  s.addText(st[0], { x: 7.2, y: 2.4 + i * 0.95, w: 1.0, h: 0.4, fontSize: 12, bold: true, color: C.gold, margin: 0 });
  s.addText(st[1], { x: 8.3, y: 2.4 + i * 0.95, w: 4.1, h: 0.85, fontSize: 11, color: C.text, margin: 0, lineSpacing: 14 });
});
s.addText('当前状态：比赛原型，未接入真实电站数据，未产生真实收益。落地需完成上述四步。', { x: 0.7, y: 6.75, w: 12, h: 0.35, fontSize: 10, color: C.gray, margin: 0 });

// ============ P14 总结 ============
s = pres.addSlide();
s.background = { color: C.bgDark };
s.addShape(pres.ShapeType.ellipse, { x: 11.0, y: 4.8, w: 4, h: 4, fill: { color: '1A2C4F' }, line: { type: 'none' } });
s.addText('总结', { x: 0.8, y: 0.8, w: 5, h: 0.9, fontSize: 40, bold: true, color: C.white, fontFace: 'Cambria', margin: 0 });
const sums = [
  { n: '01', t: '真实可验证', d: '七 Agent 真实执行、MCP 真实协议、206 项测试全绿、三个场景实际运行验证——每个声明都有代码和测试支撑。' },
  { n: '02', t: '诚实可信任', d: '模拟数据标注"模拟"、模型估算标注"model_estimate"、数据不足拒绝决策——不编造数据，不伪装成功。' },
  { n: '03', t: '稳定可演示', d: '10 项 P0 修复 + 28 项回归测试、断网/无 Key 自动降级、Windows 跨平台兼容——现场演示零风险。' },
];
sums.forEach((p, i) => {
  const y = 2.0 + i * 1.5;
  s.addText(p.n, { x: 0.8, y, w: 0.9, h: 0.8, fontSize: 36, bold: true, color: C.gold, fontFace: 'Cambria', margin: 0 });
  s.addText(p.t, { x: 1.9, y: y + 0.05, w: 3, h: 0.5, fontSize: 20, bold: true, color: C.white, margin: 0 });
  s.addText(p.d, { x: 1.9, y: y + 0.55, w: 9.5, h: 0.7, fontSize: 13, color: 'AAB8D0', margin: 0, lineSpacing: 17 });
});
s.addShape(pres.ShapeType.line, { x: 0.8, y: 6.5, w: 4, h: 0, line: { color: C.gold, width: 2 } });
s.addText('疆光 · PV-Clean-Decision  |  让每一次清洗决策有据可依', { x: 0.8, y: 6.7, w: 10, h: 0.5, fontSize: 16, color: C.white, margin: 0 });

// ============ 保存 ============
pres.writeFile({ fileName: '/workspace/PV-Clean-Decision/presentation/PV-Clean-Decision-答辩PPT.pptx' })
  .then(() => console.log('PPT 生成完成'))
  .catch(e => { console.error(e); process.exit(1); });
