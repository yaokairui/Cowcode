"""OpenAI provider for Cowcode."""

from __future__ import annotations

import json
import ssl
from typing import Any, AsyncIterator

import httpx

from cowcode.config import ProviderConfig
from cowcode.provider.base import Provider, ProviderError
from cowcode.session import Message, Session, StreamEvent, ToolCall, ToolDefinition

__all__ = ["OpenAIProvider"]


class OpenAIProvider(Provider):
    """LLM provider backed by OpenAI Chat Completions."""

    STREAM_URL = "/chat/completions"

    def __init__(self, config: ProviderConfig) -> None:
        self._base_url = config.base_url.rstrip("/")
        self._api_key = config.api_key
        self._model = config.model

    async def stream(
        self, session: Session, tools: list[ToolDefinition] | None = None
    ) -> AsyncIterator[StreamEvent]:
        """Stream text and tool-call events from OpenAI."""
        url = self._base_url + self.STREAM_URL
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._build_messages_payload(session.get_history()),
            "stream": True,
        }
        if tools:
            payload["tools"] = [self._tool_definition(tool) for tool in tools]

        tool_buffers: dict[int, dict[str, str]] = {}
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            try:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue
                        data_json = line[len("data: ") :]
                        if not data_json or data_json == "[DONE]":
                            continue

                        try:
                            data = json.loads(data_json)
                        except json.JSONDecodeError:
                            continue

                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})

                        token = delta.get("content") or ""
                        if token:
                            yield StreamEvent(text=token)

                        for tool_call in delta.get("tool_calls") or []:
                            index = int(tool_call.get("index", 0))
                            buffer = tool_buffers.setdefault(index, {})
                            if tool_call.get("id"):
                                buffer["id"] = tool_call["id"]
                            function = tool_call.get("function") or {}
                            if function.get("name"):
                                buffer["name"] = function["name"]
                            if function.get("arguments"):
                                buffer["args"] = buffer.get("args", "") + function["arguments"]

                if tool_buffers:
                    yield StreamEvent(tool_calls=self._build_tool_calls(tool_buffers))
                yield StreamEvent(done=True)
            except httpx.HTTPStatusError as exc:
                raise ProviderError(self._format_http_error(exc)) from exc
            except httpx.RequestError as exc:
                raise ProviderError(f"OpenAI request failed: {exc.__class__.__name__}") from exc

    def _build_messages_payload(self, messages: list[Message]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "tool":
                for result in message.tool_results:
                    payload.append(
                        {
                            "role": "tool",
                            "tool_call_id": result.tool_call_id,
                            "content": result.content,
                        }
                    )
                continue

            item: dict[str, Any] = {"role": message.role, "content": message.content}
            if message.role == "assistant" and message.tool_calls:
                item["content"] = message.content or None
                item["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": call.input or "{}",
                        },
                    }
                    for call in message.tool_calls
                ]
            payload.append(item)
        return payload

    @staticmethod
    def _tool_definition(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            },
        }

    @staticmethod
    def _build_tool_calls(buffers: dict[int, dict[str, str]]) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for index in sorted(buffers):
            buffer = buffers[index]
            calls.append(
                ToolCall(
                    id=buffer.get("id") or f"call_{index}",
                    name=buffer.get("name") or "",
                    input=buffer.get("args") or "{}",
                )
            )
        return calls

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        """Create an SSL context that trusts system CAs."""
        return ssl.create_default_context()

    @staticmethod
    def _format_http_error(exc: httpx.HTTPStatusError) -> str:
        body = exc.response.text.strip().replace("\n", " ")[:500]
        if body:
            return f"OpenAI API error {exc.response.status_code}: {body}"
        return f"OpenAI API error {exc.response.status_code}"
