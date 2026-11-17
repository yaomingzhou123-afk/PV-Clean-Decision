import json
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "mcp_server.py"


def _run_session(payloads: list) -> list:
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input="\n".join(json.dumps(p, ensure_ascii=False) for p in payloads) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def test_initialize_handshake():
    out = _run_session([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}])
    assert out[0]["result"]["protocolVersion"] == "2024-11-05"
    assert out[0]["result"]["serverInfo"]["name"] == "pv-agent-mcp"
    assert "tools" in out[0]["result"]["capabilities"]


def test_tools_list_has_schemas():
    out = _run_session([{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
    tools = out[0]["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"get_site_data", "search_knowledge", "calc_economics"} <= names
    for t in tools:
        assert t["description"]
        assert t["inputSchema"]["type"] == "object"


def test_tools_call_search_knowledge():
    out = _run_session([
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "search_knowledge", "arguments": {"query": "风速 高处作业 降水", "applies_to": "weather", "top_k": 2}}}
    ])
    payload = json.loads(out[0]["result"]["content"][0]["text"])
    ids = [r["id"] for r in payload["results"]]
    assert ids and ids[0].startswith("KB-A")


def test_tools_call_unknown_tool_returns_error():
    out = _run_session([
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "not_exist", "arguments": {}}}
    ])
    assert out[0]["error"]["code"] == -32601


def test_unknown_method_returns_error():
    out = _run_session([{"jsonrpc": "2.0", "id": 5, "method": "foo/bar"}])
    assert out[0]["error"]["code"] == -32601


def test_parse_error_does_not_crash():
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input="not-a-json\n" + json.dumps({"jsonrpc": "2.0", "id": 6, "method": "tools/list"}) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    lines = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
    assert lines[0]["error"]["code"] == -32700
    assert "result" in lines[1]


def test_client_roundtrip():
    from mcp_client import smoke_test

    result = smoke_test()
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "pv-agent-mcp"
    assert "search_knowledge" in result["tools"]
    assert result["kb_hits"]