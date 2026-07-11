"""OpenAI provider for Cowcode."""

from __future__ import annotations

import json
import ssl
from typing import Any, AsyncIterator

import httpx

from cowcode.config import ProviderConfig
from cowcode.provider.base import Provider, ProviderError, Request
from cowcode.session import StreamEvent, ToolCall, ToolDefinition, Usage

__all__ = ["OpenAIProvider"]


class OpenAIProvider(Provider):
    """LLM provider backed by OpenAI Chat Completions."""

    STREAM_URL = "/chat/completions"

    def __init__(self, config: ProviderConfig) -> None:
        self._base_url = config.base_url.rstrip("/")
        self._api_key = config.api_key
        self._model = config.model

    @property
    def model(self) -> str:
        return self._model

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Stream text and tool-call events from OpenAI."""
        url = self._base_url + self.STREAM_URL
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = self.build_payload(request)

        tool_buffers: dict[int, dict[str, str]] = {}
        usage_input = usage_output = cache_read = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            try:
                async with client.stream(
                    "POST", url, json=payload, headers=headers
                ) as response:
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

                        # 流末尾 usage chunk（choices 为空，带 usage）
                        choices = data.get("choices", [])
                        if not choices:
                            chunk_usage = data.get("usage")
                            if chunk_usage:
                                usage_input, usage_output, cache_read = (
                                    self._parse_usage(chunk_usage)
                                )
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
                                buffer["args"] = (
                                    buffer.get("args", "") + function["arguments"]
                                )

                if tool_buffers:
                    yield StreamEvent(tool_calls=self._build_tool_calls(tool_buffers))
                if usage_input or usage_output:
                    yield StreamEvent(
                        usage=Usage(
                            input_tokens=usage_input,
                            output_tokens=usage_output,
                            cache_read=cache_read,
                        )
                    )
                yield StreamEvent(done=True)
            except httpx.HTTPStatusError as exc:
                raise ProviderError(self._format_http_error(exc)) from exc
            except httpx.RequestError as exc:
                raise ProviderError(
                    f"OpenAI request failed: {exc.__class__.__name__}"
                ) from exc

    def build_payload(self, request: Request) -> dict[str, Any]:
        """构造可独立测试的 OpenAI 请求体。"""
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._build_messages_payload(request),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            payload["tools"] = [self._tool_definition(tool) for tool in request.tools]
        return payload

    def _build_messages_payload(self, request: Request) -> list[dict[str, Any]]:
        messages = request.messages
        payload: list[dict[str, Any]] = []
        system_text = request.system.stable
        if request.system.environment:
            system_text = (
                system_text + "\n\n" + request.system.environment
                if system_text
                else request.system.environment
            )
        if system_text:
            payload.append({"role": "system", "content": system_text})
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

            if message.role == "system":
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
        if request.reminder:
            payload.append({"role": "user", "content": request.reminder})
        return payload

    @staticmethod
    def _parse_usage(usage: Any) -> tuple[int, int, int]:
        """解析 OpenAI usage 与自动缓存命中字段。"""
        if not isinstance(usage, dict):
            return 0, 0, 0
        details = usage.get("prompt_tokens_details") or {}
        cached = (
            details.get("cached_tokens", 0) or 0 if isinstance(details, dict) else 0
        )
        return (
            usage.get("prompt_tokens", 0) or 0,
            usage.get("completion_tokens", 0) or 0,
            cached,
        )

    @staticmethod
    def _parse_usage(usage: Any) -> tuple[int, int, int]:
        """解析 OpenAI usage 与自动缓存命中字段。"""
        if not isinstance(usage, dict):
            return 0, 0, 0
        details = usage.get("prompt_tokens_details") or {}
        cached = (
            details.get("cached_tokens", 0) or 0 if isinstance(details, dict) else 0
        )
        return (
            usage.get("prompt_tokens", 0) or 0,
            usage.get("completion_tokens", 0) or 0,
            cached,
        )

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
