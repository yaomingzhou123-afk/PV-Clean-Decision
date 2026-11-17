"""V3.0 第七阶段：MCP Client/Server 工程质量测试。

覆盖：读超时生效、握手失败不泄漏子进程、close 幂等、参数校验错误码、
calc_economics 缺省参数可执行、工具定义与执行逻辑一致。
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from mcp_client import MCPClient
from mcp_server import TOOLS, handle

SERVER_PATH = Path(__file__).resolve().parents[1] / "mcp_server.py"


SLOW_SERVER = textwrap.dedent(
    """
    import sys
    for line in sys.stdin:
        pass
    """
)

EXIT_SERVER = textwrap.dedent(
    """
    import sys
    sys.exit(1)
    """
)


def _run_session(requests):
    proc = subprocess.run(
        [sys.executable, str(SERVER_PATH)],
        input="".join(json.dumps(r) + "\n" for r in requests),
        capture_output=True,
        text=True,
        timeout=60,
    )
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


def test_tool_definitions_match_execution_paths():
    """工具定义与 _call_tool 分支一一对应，不虚构工具。"""
    names = {t["name"] for t in TOOLS}
    assert names == {"get_site_data", "search_knowledge", "calc_economics"}
    for tool in TOOLS:
        assert tool["description"]
        assert isinstance(tool["inputSchema"], dict)


def test_client_read_timeout_is_enforced(tmp_path):
    slow = tmp_path / "slow_server.py"
    slow.write_text(SLOW_SERVER, encoding="utf-8")
    client = MCPClient(timeout=0.5, server_path=slow)
    try:
        with pytest.raises(TimeoutError, match="超时"):
            client.request("initialize", {})
    finally:
        client.close()
    assert client.proc.poll() is not None


def test_client_handshake_failure_does_not_leak(tmp_path):
    exiting = tmp_path / "exit_server.py"
    exiting.write_text(EXIT_SERVER, encoding="utf-8")
    client = MCPClient(timeout=3, server_path=exiting)
    with pytest.raises(RuntimeError):
        client.initialize()
    client.close()
    assert client.proc.poll() is not None


def test_client_close_is_idempotent():
    with MCPClient() as client:
        client.initialize()
    assert client.proc.poll() is not None
    client.close()
    client.close()
    assert client.proc.poll() is not None


def test_server_rejects_invalid_lat_with_32602():
    responses = _run_session(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_site_data", "arguments": {"lat": 999, "mode": "demo"}}}]
    )
    assert responses[0]["error"]["code"] == -32602
    assert "lat" in responses[0]["error"]["message"]


def test_server_rejects_empty_query_with_32602():
    responses = _run_session(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_knowledge", "arguments": {"query": ""}}}]
    )
    assert responses[0]["error"]["code"] == -32602


def test_server_rejects_out_of_range_top_k_with_32602():
    responses = _run_session(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search_knowledge", "arguments": {"query": "风速", "top_k": 99}}}]
    )
    assert responses[0]["error"]["code"] == -32602


def test_server_rejects_unknown_tool_with_32601():
    responses = _run_session(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}}]
    )
    assert responses[0]["error"]["code"] == -32601


def test_server_calc_economics_works_without_config_and_context():
    """calc_economics 缺省参数可执行：使用服务端默认配置 + demo 数据。"""
    responses = _run_session(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "calc_economics", "arguments": {"mode": "demo"}}}]
    )
    result = responses[0].get("result", {})
    text = result["content"][0]["text"]
    metrics = json.loads(text)
    assert metrics["decision"]["action"] is not None
    assert metrics["economics"]["net_gain"] is not None


def test_server_calc_economics_rejects_non_dict_config():
    responses = _run_session(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "calc_economics", "arguments": {"config": "not-a-dict"}}}]
    )
    assert responses[0]["error"]["code"] == -32602


def test_server_parse_error_returns_32700():
    proc = subprocess.run(
        [sys.executable, str(SERVER_PATH)],
        input="not-json\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    resp = json.loads(proc.stdout.strip().splitlines()[-1])
    assert resp["error"]["code"] == -32700


def test_handle_unknown_method_returns_32601():
    resp = handle({"jsonrpc": "2.0", "id": 9, "method": "no/such/method"})
    assert resp["error"]["code"] == -32601
