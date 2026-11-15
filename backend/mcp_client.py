import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SERVER = BASE_DIR / "mcp_server.py"


class MCPClient:
    def __init__(self, timeout: float = 30.0):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            bufsize=1,
        )
        self.timeout = timeout
        self._next_id = 0
        self.server_info = {}

    def _send(self, payload: dict) -> dict | None:
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        if payload.get("id") is None:
            return None
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed the connection")
        return json.loads(line)

    def request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params
        resp = self._send(payload)
        if "error" in resp:
            raise RuntimeError(resp["error"].get("message", "MCP error"))
        return resp["result"]

    def notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def initialize(self) -> dict:
        result = self.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "pv-agent", "version": "1.0.0"}})
        self.server_info = result.get("serverInfo", {})
        self.notify("notifications/initialized")
        return result

    def list_tools(self) -> list:
        return self.request("tools/list").get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content") or []
        for block in content:
            if block.get("type") == "text":
                return json.loads(block["text"])
        return {}

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.terminate()
            self.proc.wait(timeout=3)
        except Exception:
            self.proc.kill()


def smoke_test() -> dict:
    client = MCPClient()
    try:
        init = client.initialize()
        tools = client.list_tools()
        kb = client.call_tool("search_knowledge", {"query": "风速 高处作业", "applies_to": "weather", "top_k": 2})
        return {
            "protocolVersion": init.get("protocolVersion"),
            "serverInfo": init.get("serverInfo"),
            "tools": [t["name"] for t in tools],
            "kb_hits": [r["id"] for r in kb.get("results", [])],
        }
    finally:
        client.close()


if __name__ == "__main__":
    print(json.dumps(smoke_test(), ensure_ascii=False, indent=2))