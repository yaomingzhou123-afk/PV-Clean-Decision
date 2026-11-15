import json
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from kb.retriever import retrieve
from weather import demo_context, fetch_context
from pv_model import compute_metrics

SERVER_INFO = {"name": "pv-agent-mcp", "version": "1.0.0"}
PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "get_site_data",
        "description": "获取光伏站点气象、沙尘与 PVGIS 理论发电量数据；mode=demo 时返回离线样例",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "loss_pct": {"type": "number", "default": 10},
                "mode": {"type": "string", "enum": ["live", "demo"], "default": "live"},
            },
            "required": [],
        },
    },
    {
        "name": "search_knowledge",
        "description": "检索光伏运维知识库，返回条款 id、摘要、来源与核实状态",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "applies_to": {"type": "string"},
                "top_k": {"type": "integer", "default": 2},
            },
            "required": ["query"],
        },
    },
    {
        "name": "calc_economics",
        "description": "基于配置与数据上下文计算发电量、污损损失、收益与决策结论",
        "inputSchema": {
            "type": "object",
            "properties": {
                "config": {"type": "object"},
                "context": {"type": "object"},
            },
            "required": ["config", "context"],
        },
    },
]


def _text(payload) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}]}


def _call_tool(name: str, args: dict) -> dict:
    if name == "get_site_data":
        if args.get("mode", "live") == "demo":
            return _text(demo_context())
        import asyncio

        ctx = asyncio.run(
            fetch_context(
                float(args.get("lat", 44.01)),
                float(args.get("lng", 87.31)),
                float(args.get("loss_pct", 10)),
            )
        )
        return _text(ctx)
    if name == "search_knowledge":
        query = args.get("query", "")
        applies_to = args.get("applies_to")
        top_k = int(args.get("top_k", 2))
        return _text({"results": retrieve(query, applies_to=applies_to, top_k=top_k)})
    if name == "calc_economics":
        metrics = compute_metrics(args["config"], args["context"])
        return _text(metrics)
    raise KeyError(f"unknown tool: {name}")


def handle(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = req.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = _call_tool(name, args)
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        except KeyError as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": str(e)},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"},
            }
    if req_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"unknown method: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()