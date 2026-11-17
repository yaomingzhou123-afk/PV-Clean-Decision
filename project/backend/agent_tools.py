from kb.retriever import retrieve
from pv_model import compute_metrics
from weather import demo_context, fetch_context

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_site_data",
            "description": "获取光伏站点的气象、沙尘与 PVGIS 理论发电量数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {"type": "number", "description": "纬度"},
                    "lng": {"type": "number", "description": "经度"},
                    "mode": {"type": "string", "enum": ["live", "demo"], "description": "数据模式"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "检索光伏运维知识库，返回安全规程、污损机理、清洗工艺等条款",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词"},
                    "applies_to": {"type": "string", "description": "限定 Agent 场景，如 weather/soiling/economics/ops"},
                    "top_k": {"type": "integer", "description": "返回条数，默认 2"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc_economics",
            "description": "根据电站配置与数据上下文计算污损损失、清洗收益与决策结论",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["live", "demo"], "description": "数据模式"},
                },
                "required": [],
            },
        },
    },
]


def dispatch(name: str, args: dict, config: dict) -> dict:
    if name == "get_site_data":
        mode = args.get("mode") or config.get("scenario", "demo")
        if mode == "demo":
            return demo_context()
        import asyncio

        return asyncio.run(
            fetch_context(
                float(args.get("lat", config["site"]["lat"])),
                float(args.get("lng", config["site"]["lng"])),
                float(config["economics"].get("pvgis_loss_pct", 10)),
            )
        )
    if name == "search_knowledge":
        return {
            "results": retrieve(
                args.get("query", ""),
                applies_to=args.get("applies_to"),
                top_k=int(args.get("top_k", 2)),
            )
        }
    if name == "calc_economics":
        mode = args.get("mode") or config.get("scenario", "demo")
        # P0-2 修复：mode 与 config.scenario 解耦时强制同步，
        # 确保 pv_model 的降级防线（scenario=="live" + fallback）能正确触发
        if mode != config.get("scenario"):
            config = {**config, "scenario": mode}
        context = demo_context() if mode == "demo" else dispatch("get_site_data", {"mode": "live"}, config)
        return compute_metrics(config, context)
    raise KeyError(f"unknown tool: {name}")