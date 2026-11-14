import asyncio
import json
import os

import httpx

from agent_tools import TOOL_SCHEMAS
import llm


async def probe() -> dict:
    result = {
        "base_url": llm.BASE_URL,
        "endpoint": llm.endpoint(),
        "model": llm.MODEL,
        "configured": llm.enabled(),
    }
    if not llm.enabled():
        result["hint"] = "请先设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL"
        return result

    async with httpx.AsyncClient(timeout=llm.TIMEOUT) as client:
        try:
            r1 = await client.post(
                llm.endpoint(),
                headers=llm.headers(),
                json={"model": llm.MODEL, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 16},
            )
            result["chat_http"] = r1.status_code
            body = r1.json()
            msg = (body.get("choices") or [{}])[0].get("message") or {}
            result["chat_reply"] = (msg.get("content") or "")[:80]
        except Exception as e:
            result["chat_error"] = f"{type(e).__name__}: {e}"
            return result

        try:
            r2 = await client.post(
                llm.endpoint(),
                headers=llm.headers(),
                json={
                    "model": llm.MODEL,
                    "messages": [{"role": "user", "content": "帮我查一下昌吉明天的天气"}],
                    "tools": TOOL_SCHEMAS[:1],
                    "tool_choice": "auto",
                    "max_tokens": 128,
                },
            )
            result["tools_http"] = r2.status_code
            body2 = r2.json()
            msg2 = (body2.get("choices") or [{}])[0].get("message") or {}
            calls = msg2.get("tool_calls") or []
            result["tools_supported"] = bool(calls)
            result["tool_calls"] = [
                {"name": (c.get("function") or {}).get("name")} for c in calls
            ]
            if not calls:
                result["message_keys"] = list(msg2.keys())
                result["sample"] = (msg2.get("content") or "")[:120]
        except Exception as e:
            result["tools_error"] = f"{type(e).__name__}: {e}"
    return result


if __name__ == "__main__":
    out = asyncio.run(probe())
    print(json.dumps(out, ensure_ascii=False, indent=2))