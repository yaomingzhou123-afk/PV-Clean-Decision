import os

from env_loader import load_env

load_env()

import httpx

BASE_URL = os.getenv("LLM_BASE_URL", "").rstrip("/")
API_KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "")
CHAT_PATH = os.getenv("LLM_CHAT_PATH", "/chat/completions")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))


def enabled() -> bool:
    return bool(BASE_URL and API_KEY and MODEL)


def endpoint() -> str:
    if BASE_URL.endswith("/chat/completions"):
        return BASE_URL
    return BASE_URL + CHAT_PATH


def headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def _payload(messages: list, tools: list | None = None, tool_choice: str = "auto", temperature: float = 0.3, max_tokens: int | None = None) -> dict:
    payload = {"model": MODEL, "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return payload


async def raw_chat(
    messages: list,
    tools: list | None = None,
    tool_choice: str = "auto",
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> dict | None:
    if not enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                endpoint(),
                headers=headers(),
                json=_payload(messages, tools, tool_choice, temperature, max_tokens),
            )
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                return None
            return choices[0].get("message")
    except Exception:
        return None


async def chat(system: str, user: str, temperature: float = 0.4) -> str | None:
    msg = await raw_chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=temperature,
    )
    if not msg:
        return None
    content = (msg.get("content") or "").strip()
    return content or None


def mode() -> str:
    return "llm" if enabled() else "rule"