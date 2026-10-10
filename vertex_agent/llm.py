from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx


class ModelError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, timeout_sec: float):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_sec, connect=10.0))

    async def aclose(self) -> None:
        await self.client.aclose()

    async def tags(self) -> list[dict]:
        response = await self.client.get(f"{self.base_url}/api/tags", timeout=5.0)
        response.raise_for_status()
        return list(response.json().get("models") or [])

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
        try:
            async for event in self._chat_once(
                model=model,
                messages=messages,
                temperature=temperature,
                num_ctx=num_ctx,
                num_predict=num_predict,
                tools=tools,
                think=think,
            ):
                yield event
        except ModelError as exc:
            if not think or "does not support thinking" not in str(exc).lower():
                raise
            yield {"type": "progress", "text": "该模型不支持深度思考，改为直接生成"}
            async for event in self._chat_once(
                model=model,
                messages=messages,
                temperature=temperature,
                num_ctx=num_ctx,
                num_predict=num_predict,
                tools=tools,
                think=False,
            ):
                yield event

    async def _chat_once(
        self,
        *,
        model: str,
        messages: list[dict],
        temperature: float,
        num_ctx: int,
        num_predict: int,
        tools: list[dict] | None,
        think: bool,
    ) -> AsyncIterator[dict]:
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
        }
        if think:
            payload["think"] = True
        if tools:
            payload["tools"] = tools
        content_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_calls: list[dict] = []
        try:
            async with self.client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                if response.status_code >= 400:
                    raw = (await response.aread()).decode("utf-8", errors="replace")
                    raise ModelError(_explain(response.status_code, raw))
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise ModelError(str(data["error"]))
                    message = data.get("message") or {}
                    thought = message.get("thinking") or ""
                    delta = message.get("content") or ""
                    if thought:
                        thinking_parts.append(thought)
                        yield {"type": "thinking", "text": thought}
                    if delta:
                        content_parts.append(delta)
                        yield {"type": "token", "text": delta}
                    if message.get("tool_calls"):
                        tool_calls = message["tool_calls"]
                    if data.get("done"):
                        yield {
                            "type": "turn",
                            "content": "".join(content_parts),
                            "thinking": "".join(thinking_parts),
                            "tool_calls": message.get("tool_calls") or tool_calls or [],
                        }
        except httpx.ConnectError as exc:
            raise ModelError("连不上本机 Ollama。请先打开 Ollama，再刷新页面。") from exc
        except httpx.TimeoutException as exc:
            raise ModelError("模型响应超时。可以换一个更小的本地模型，或把任务拆短。") from exc


class ChatRouter:
    """Ollama 与 DeepSeek 官方 API 共用同一套对话接口。"""

    def __init__(self, base_url: str, timeout_sec: float, data_dir: Path):
        self.ollama = OllamaClient(base_url, timeout_sec)
        from vertex_agent.deepseek import DeepSeekClient

        self.deepseek = DeepSeekClient(data_dir, timeout_sec)

    async def aclose(self) -> None:
        await self.ollama.aclose()
        await self.deepseek.aclose()

    async def tags(self) -> list[dict]:
        return await self.ollama.tags()

    async def chat(self, *, model: str, **kwargs) -> AsyncIterator[dict]:
        from vertex_agent.secrets import is_deepseek_model

        client = self.deepseek if is_deepseek_model(model) else self.ollama
        async for event in client.chat(model=model, **kwargs):
            yield event


def _explain(status: int, raw: str) -> str:
    if status == 402:
        return "模型云端接口返回 402，当前账号没有开通这个模型。请在页面右上角改用本机已下载的模型。"
    return f"模型接口 {status}：{raw[:400]}"
