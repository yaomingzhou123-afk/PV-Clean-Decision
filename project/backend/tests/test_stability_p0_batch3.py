"""批次 3（P0-9 + P1）：PVGIS 敏感性修复与文档一致性回归测试。"""

import json
from pathlib import Path

from pv_model import compute_metrics

CONFIG_PATH = Path(__file__).parent.parent / "data" / "pv_config.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _ctx(theoretical=None):
    days = [{"date": f"D{i+1}", "irradiance": 5.8, "rain": 0.0, "wind": 9.0, "cloud": 0} for i in range(3)]
    return {
        "forecast": {"days": days, "source": "test", "quality": "demo", "fetched_at": "t"},
        "air": {"pm10": 135.0, "dust": 120.0, "quality": "demo", "source": "test"},
        "theoretical": theoretical,
        "quality": "demo",
        "fetched_at": "t",
        "data_source_records": [],
    }


def test_p0_9_pvgis_generation_sensitivity_is_effective():
    """PVGIS 模式下"发电水平 ±20%"应产生不同的净收益（扰动 E_d）。"""
    ctx = _ctx(theoretical={"E_d": 3.79, "month": 11, "radiation_db": "PVGIS-ERA5", "year_min": 2005, "year_max": 2023})
    m = compute_metrics(CONFIG, ctx, include_sensitivity=True)
    gen_scenarios = [s for s in m["sensitivity"]["scenarios"] if s["param"] == "发电水平"]
    assert len(gen_scenarios) == 2
    nets = {s["net_gain"] for s in gen_scenarios}
    assert len(nets) == 2, f"PVGIS 模式下发电水平 ±20% 净收益应不同，实际均为 {nets}"
    assert gen_scenarios[0]["net_gain"] != m["economics"]["net_gain"], "扰动结果应不同于基准"


def test_p0_9_formula_generation_sensitivity_still_works():
    """降级公式模式下"发电水平 ±20%"仍通过 efficiency 扰动生效（不误伤）。"""
    ctx = _ctx(theoretical=None)
    m = compute_metrics(CONFIG, ctx, include_sensitivity=True)
    gen_scenarios = [s for s in m["sensitivity"]["scenarios"] if s["param"] == "发电水平"]
    nets = {s["net_gain"] for s in gen_scenarios}
    assert len(nets) == 2, f"公式模式下发电水平 ±20% 净收益应不同，实际均为 {nets}"


def test_p0_9_sensitivity_context_not_mutated():
    """敏感性分析不得污染原始 context（deep copy 验证）。"""
    theoretical = {"E_d": 3.79, "month": 11, "radiation_db": "PVGIS-ERA5", "year_min": 2005, "year_max": 2023}
    ctx = _ctx(theoretical=theoretical)
    m = compute_metrics(CONFIG, ctx, include_sensitivity=True)
    assert ctx["theoretical"]["E_d"] == 3.79, "敏感性分析后原始 context 的 E_d 不应被修改"
    assert m["economics"]["theory_mwh_day"] is not None
