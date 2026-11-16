import json
import logging
import os
import select
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SERVER = BASE_DIR / "mcp_server.py"

logger = logging.getLogger("pv.mcp.client")


class MCPClient:
    """MCP JSON-RPC 客户端：子进程 stdio 通信，带读超时与幂等关闭。"""

    def __init__(self, timeout: float = 30.0, server_path: str | Path | None = None):
        self.server_path = Path(server_path) if server_path else SERVER
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        self.proc = subprocess.Popen(
            [sys.executable, str(self.server_path)],
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
        self._closed = False
        self.server_info = {}

    def _readline_timeout(self) -> str:
        """带超时读取一行响应；超时抛 TimeoutError，连接关闭抛 RuntimeError。"""
        deadline = select.select([self.proc.stdout], [], [], self.timeout)
        if not deadline[0]:
            raise TimeoutError(f"MCP 响应超时（{self.timeout}s）")
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed the connection")
        return line

    def _send(self, payload: dict) -> dict | None:
        if self._closed:
            raise RuntimeError("MCP client is closed")
        try:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError) as e:
            raise RuntimeError(f"MCP server pipe broken: {e}") from e
        if payload.get("id") is None:
            return None
        return json.loads(self._readline_timeout())

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
        result = self.request(
            "initialize",
            {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "pv-agent", "version": "1.0.0"}},
        )
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
        if self._closed:
            return
        self._closed = True
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=3)
        except Exception:
            logger.exception("关闭 MCP 子进程时出错")
            try:
                self.proc.kill()
            except Exception:
                pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def smoke_test() -> dict:
    with MCPClient() as client:
        init = client.initialize()
        tools = client.list_tools()
        kb = client.call_tool("search_knowledge", {"query": "风速 高处作业", "applies_to": "weather", "top_k": 2})
        return {
            "protocolVersion": init.get("protocolVersion"),
            "serverInfo": init.get("serverInfo"),
            "tools": [t["name"] for t in tools],
            "kb_hits": [r["id"] for r in kb.get("results", [])],
        }


if __name__ == "__main__":
    print(json.dumps(smoke_test(), ensure_ascii=False, indent=2))
