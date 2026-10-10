from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from vertex_agent.llm import ModelError
from vertex_agent.secrets import BASE_URL, MODEL_ID, api_model_id, load_api_key

COMPLETIONS = f"{BASE_URL}/chat/completions"


class DeepSeekClient:
    def __init__(self, data_dir: Path, timeout_sec: float):
        self.data_dir = data_dir
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec, connect=15.0))

    async def aclose(self) -> None:
        await self.client.aclose()

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        temperature: float,
        num_ctx: int,
        num_predict: int,
        tools: list[dict] | None = None,
        think: bool = False,
    ) -> AsyncIterator[dict]:
        del num_ctx
        api_key = load_api_key(self.data_dir)
        if not api_key:
            raise ModelError("还没有在本机注册 DeepSeek API Key。请在左侧填入 Key 并点「注册到本机」。")
        payload: dict = {
            "model": api_model_id(model),
            "messages": adapt_messages(messages),
            "stream": True,
            "max_tokens": num_predict,
            "thinking": {"type": "enabled" if think else "disabled"},
        }
        if think:
            payload["reasoning_effort"] = "high"
        else:
            payload["temperature"] = temperature
        if tools:
            payload["tools"] = tools
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_slots: dict[int, dict[str, str]] = {}
        try:
            async with self.client.stream(
                "POST",
                COMPLETIONS,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    raw = (await response.aread()).decode("utf-8", errors="replace")
                    raise ModelError(_explain(response.status_code, raw))
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    error = event.get("error")
                    if error:
                        message = error.get("message") if isinstance(error, dict) else str(error)
                        raise ModelError(message or "DeepSeek 返回错误")
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    thought = delta.get("reasoning_content") or ""
                    text = delta.get("content") or ""
                    if thought:
                        thinking_parts.append(thought)
                        yield {"type": "thinking", "text": thought}
                    if text:
                        content_parts.append(text)
                        yield {"type": "token", "text": text}
                    for call in delta.get("tool_calls") or []:
                        _merge_tool_delta(tool_slots, call)
        except httpx.ConnectError as exc:
            raise ModelError("连不上 DeepSeek API。请检查这台电脑的网络。") from exc
        except httpx.TimeoutException as exc:
            raise ModelError("DeepSeek V4.1 Flash 响应超时。可以把任务拆短后再试。") from exc
        yield {
            "type": "turn",
            "content": "".join(content_parts),
            "thinking": "".join(thinking_parts),
            "tool_calls": _finish_tools(tool_slots),
        }


async def verify_api_key(api_key: str) -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        try:
            response = await client.post(
                COMPLETIONS,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": MODEL_ID,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                    "stream": False,
                    "thinking": {"type": "disabled"},
                },
            )
        except httpx.HTTPError as exc:
            raise ModelError("连不上 DeepSeek API，Key 还没有保存。") from exc
    if response.status_code == 401:
        raise ModelError("DeepSeek 没有接受这个 Key。请核对后再注册。")
    if response.status_code == 402:
        raise ModelError("Key 已被拒绝：账户余额不足。")
    if response.status_code >= 400:
        raise ModelError(f"DeepSeek 返回 {response.status_code}，Key 还没有保存。")


def adapt_messages(messages: list[dict]) -> list[dict]:
    adapted = []
    for message in messages:
        role = message.get("role")
        content = message.get("content") or ""
        images = [item for item in (message.get("images") or []) if isinstance(item, str) and item.startswith("data:image/")]
        if role == "user" and images:
            parts = []
            if content:
                parts.append({"type": "text", "text": content})
            for url in images:
                parts.append({"type": "image_url", "image_url": {"url": url}})
            item = {"role": role, "content": parts}
        else:
            item = {"role": role, "content": content}
        reasoning = message.get("reasoning_content") or message.get("thinking") or ""
        if reasoning and role == "assistant":
            item["reasoning_content"] = reasoning
        if role == "assistant" and message.get("tool_calls"):
            calls = []
            for index, call in enumerate(message["tool_calls"]):
                function = call.get("function") or {}
                arguments = function.get("arguments")
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments or {}, ensure_ascii=False)
                calls.append(
                    {
                        "id": call.get("id") or f"call_{index}",
                        "type": "function",
                        "function": {"name": function.get("name") or "", "arguments": arguments},
                    }
                )
            item["tool_calls"] = calls
        if role == "tool":
            item["tool_call_id"] = message.get("tool_call_id") or ""
        adapted.append(item)
    return adapted


def _merge_tool_delta(slots: dict[int, dict[str, str]], call: dict) -> None:
    index = int(call.get("index") or 0)
    slot = slots.setdefault(index, {"id": "", "name": "", "arguments": ""})
    if call.get("id"):
        slot["id"] = call["id"]
    function = call.get("function") or {}
    if function.get("name"):
        slot["name"] += function["name"]
    if function.get("arguments"):
        slot["arguments"] += function["arguments"]


def _finish_tools(slots: dict[int, dict[str, str]]) -> list[dict]:
    calls = []
    for index in sorted(slots):
        slot = slots[index]
        raw_arguments = slot["arguments"]
        try:
            arguments = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError:
            arguments = raw_arguments
        calls.append(
            {
                "id": slot["id"] or f"call_{index}",
                "type": "function",
                "function": {"name": slot["name"], "arguments": arguments},
            }
        )
    return calls


def _explain(status: int, raw: str) -> str:
    if status == 401:
        return "DeepSeek 拒绝了已保存的 Key。请在左侧重新注册。"
    if status == 402:
        return "DeepSeek 账户余额不足，暂时无法调用 V4.1 Flash。"
    if status == 429:
        return "DeepSeek 请求过于频繁，请稍后再试。"
    return f"DeepSeek 接口 {status}：{raw[:240]}"
