import llm


def test_endpoint_appends_chat_path(monkeypatch):
    monkeypatch.setattr(llm, "BASE_URL", "https://api.modelarts-maas.com/v2")
    assert llm.endpoint() == "https://api.modelarts-maas.com/v2/chat/completions"


def test_endpoint_accepts_full_url(monkeypatch):
    monkeypatch.setattr(llm, "BASE_URL", "https://api.modelarts-maas.com/v2/chat/completions")
    assert llm.endpoint() == "https://api.modelarts-maas.com/v2/chat/completions"


def test_headers_use_bearer(monkeypatch):
    monkeypatch.setattr(llm, "API_KEY", "test-key")
    assert llm.headers()["Authorization"] == "Bearer test-key"


def test_enabled_requires_all_three(monkeypatch):
    monkeypatch.setattr(llm, "BASE_URL", "https://x/v2")
    monkeypatch.setattr(llm, "API_KEY", "")
    monkeypatch.setattr(llm, "MODEL", "m")
    assert llm.enabled() is False


def test_payload_includes_tools(monkeypatch):
    monkeypatch.setattr(llm, "MODEL", "deepseek-v4.1-flash-1017")
    tools = [{"type": "function", "function": {"name": "x", "parameters": {}}}]
    payload = llm._payload([{"role": "user", "content": "hi"}], tools=tools)
    assert payload["model"] == "deepseek-v4.1-flash-1017"
    assert payload["tools"] == tools
    assert payload["tool_choice"] == "auto"