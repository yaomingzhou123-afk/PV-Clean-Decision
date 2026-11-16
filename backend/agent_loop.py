import asyncio
import json
import logging

import llm
from agent_tools import TOOL_SCHEMAS, dispatch
from mcp_client import MCPClient
from orchestrator import envelope, load_config

logger = logging.getLogger("pv.agent_loop")

SYSTEM_PROMPT = (
    "你是光伏电站运维决策助手。回答前先判断是否需要调用工具获取真实数据，"
    "不要凭记忆编造价格、辐照或损失率。必要时调用 get_site_data、search_knowledge、calc_economics。"
    "凡是涉及金额、发电量、污损损失率、回本周期的结论，必须先调用 calc_economics 取得结果，"
    "不得自行估算；回答中的数字必须来自工具返回，并注明依据来源。"
    "最后用不超过 150 字给出结论。"
)


async def _exec_tool(mcp, name: str, args: dict, config: dict) -> dict:
    if mcp:
        try:
            if name == "get_site_data":
                args.setdefault("lat", config["site"]["lat"])
                args.setdefault("lng", config["site"]["lng"])
                args.setdefault("loss_pct", config["economics"].get("pvgis_loss_pct", 10))
                args.setdefault("mode", config.get("scenario", "demo"))
            if name == "calc_economics":
                args.setdefault("config", config)
                args.setdefault("mode", config.get("scenario", "demo"))
            return await asyncio.to_thread(mcp.call_tool, name, args)
        except Exception as e:
            logger.warning("MCP 工具调用失败，回退进程内直连：%s %s: %s", name, type(e).__name__, e)
    return await asyncio.to_thread(dispatch, name, args, config)


async def stream_agent(question: str, overrides: dict | None = None, max_steps: int = 4):
    config = load_config(overrides)
    yield envelope("agent_start", question=question, mode=llm.mode(), max_steps=max_steps)
    if not llm.enabled():
        yield envelope("agent_error", message="未配置 LLM，无法演示 Function Calling")
        return

    mcp = None
    try:
        mcp = MCPClient()
        init = await asyncio.to_thread(mcp.initialize)
        tools = await asyncio.to_thread(mcp.list_tools)
        yield envelope(
            "agent_mcp_ready",
            server=(init.get("serverInfo") or {}).get("name"),
            tools=[t["name"] for t in tools],
        )
    except Exception as e:
        if mcp:
            try:
                await asyncio.to_thread(mcp.close)
            except Exception:
                logger.exception("关闭失败的 MCP 子进程时出错")
            mcp = None
        logger.warning("Agent MCP 初始化失败：%s: %s", type(e).__name__, e)
        yield envelope("agent_mcp_error", message=f"{type(e).__name__}: {e}")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        for step in range(1, max_steps + 1):
            msg = await llm.raw_chat(messages, tools=TOOL_SCHEMAS, temperature=0.2)
            if msg is None:
                yield envelope("agent_error", message="模型调用失败（鉴权、地址、超时或响应格式不符）")
                return
            tool_calls = msg.get("tool_calls") or []
            content = (msg.get("content") or "").strip()
            if not tool_calls:
                yield envelope("agent_answer", answer=content, steps=step)
                return

            yield envelope(
                "agent_decision",
                step=step,
                reasoning=content,
                tools=[(tc.get("function") or {}).get("name") for tc in tool_calls],
            )
            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except Exception:
                    args = {}
                yield envelope("agent_tool_call", step=step, call_id=tc.get("id"), tool=name, arguments=args)
                try:
                    result = await _exec_tool(mcp, name, args, config)
                    ok = True
                except Exception as e:
                    result = {"error": f"{type(e).__name__}: {e}"}
                    ok = False
                yield envelope("agent_tool_result", step=step, call_id=tc.get("id"), tool=name, ok=ok, result=result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        yield envelope("agent_error", message=f"达到最大步数 {max_steps}，未收敛")
    finally:
        if mcp:
            await asyncio.to_thread(mcp.close)