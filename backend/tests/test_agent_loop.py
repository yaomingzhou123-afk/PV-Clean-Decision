import asyncio
import json

import agent_loop


def _run(question, monkeypatch, responses, config_overrides=None):
    seq = list(responses)

    async def fake_raw_chat(messages, tools=None, tool_choice="auto", temperature=0.3, max_tokens=None):
        return seq.pop(0)

    async def fake_exec(mcp, name, args, config):
        return {"tool": name, "args": args, "ok": True}

    monkeypatch.setattr(agent_loop.llm, "enabled", lambda: True)
    monkeypatch.setattr(agent_loop.llm, "raw_chat", fake_raw_chat)
    monkeypatch.setattr(agent_loop.llm, "mode", lambda: "llm")
    monkeypatch.setattr(agent_loop, "_exec_tool", fake_exec)
    monkeypatch.setattr(agent_loop, "MCPClient", lambda: (_ for _ in ()).throw(RuntimeError("no mcp")))

    events = []

    async def collect():
        async for evt in agent_loop.stream_agent(question, config_overrides or {"scenario": "demo"}):
            events.append(evt)

    asyncio.run(collect())
    return events


def test_tool_call_then_answer(monkeypatch):
    responses = [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "get_site_data", "arguments": "{\"mode\":\"demo\"}"}}
        ]},
        {"role": "assistant", "content": "已获取数据，建议清洗。"},
    ]
    events = _run("查昌吉天气", monkeypatch, responses)
    types = [e["type"] for e in events]
    assert "agent_start" in types
    assert "agent_decision" in types
    assert "agent_tool_call" in types
    assert "agent_tool_result" in types
    assert "agent_answer" in types
    call = next(e for e in events if e["type"] == "agent_tool_call")
    assert call["tool"] == "get_site_data"
    assert call["arguments"]["mode"] == "demo"
    answer = next(e for e in events if e["type"] == "agent_answer")
    assert "建议清洗" in answer["answer"]


def test_answer_without_tool_calls(monkeypatch):
    events = _run("你好", monkeypatch, [{"role": "assistant", "content": "你好，我是运维助手。"}])
    types = [e["type"] for e in events]
    assert "agent_tool_call" not in types
    assert any(e["type"] == "agent_answer" for e in events)


def test_llm_failure_reports_error(monkeypatch):
    events = _run("查天气", monkeypatch, [None])
    types = [e["type"] for e in events]
    assert "agent_error" in types


def test_disabled_llm_reports_error(monkeypatch):
    monkeypatch.setattr(agent_loop.llm, "enabled", lambda: False)
    monkeypatch.setattr(agent_loop.llm, "mode", lambda: "rule")
    events = []

    async def collect():
        async for evt in agent_loop.stream_agent("hi", {"scenario": "demo"}):
            events.append(evt)

    asyncio.run(collect())
    assert events[-1]["type"] == "agent_error"