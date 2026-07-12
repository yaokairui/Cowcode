"""Anthropic Claude provider for Cowcode."""

from __future__ import annotations

import json
import ssl
from typing import Any, AsyncIterator

import httpx

from cowcode.config import ProviderConfig
from cowcode.provider.base import Provider, ProviderError, PromptTooLongError, Request
from cowcode.session import Message, StreamEvent, ToolCall, ToolDefinition, Usage

__all__ = ["AnthropicProvider"]


class AnthropicProvider(Provider):
    """LLM provider backed by Anthropic Messages API."""

    API_VERSION = "2023-06-01"
    STREAM_URL = "/v1/messages"

    def __init__(self, config: ProviderConfig) -> None:
        self._base_url = config.base_url.rstrip("/")
        self._api_key = config.api_key
        self._model = config.model
        self._thinking = config.thinking

    @property
    def model(self) -> str:
        return self._model

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Stream visible text and tool-call events from Claude."""
        payload = self.build_payload(request)
        url = self._base_url + self.STREAM_URL
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        tool_blocks: dict[int, dict[str, str]] = {}
        usage_input = usage_output = cache_write = cache_read = 0
        async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
            try:
                async with client.stream(
                    "POST", url, json=payload, headers=headers
                ) as response:
                    response.raise_for_status()
                    event_name = ""
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("event: "):
                            event_name = line[len("event: ") :].strip()
                            continue
                        if not line.startswith("data: "):
                            continue

                        data_json = line[len("data: ") :]
                        if not data_json or data_json == "{}":
                            continue
                        try:
                            data = json.loads(data_json)
                        except json.JSONDecodeError:
                            continue

                        if event_name == "message_start":
                            usg = data.get("message", {}).get("usage") or {}
                            usage_input, cache_write, cache_read = (
                                self._parse_start_usage(usg)
                            ) or 0
                            cache_write = usg.get("cache_creation_input_tokens", 0) or 0
                            cache_read = usg.get("cache_read_input_tokens", 0) or 0
                        elif event_name == "content_block_start":
                            self._handle_block_start(data, tool_blocks)
                        elif event_name == "content_block_delta":
                            event = self._handle_block_delta(data, tool_blocks)
                            if event is not None:
                                yield event
                        elif event_name == "message_delta":
                            usage_output = self._parse_output_usage(data.get("usage"))

                if tool_blocks:
                    yield StreamEvent(tool_calls=self._build_tool_calls(tool_blocks))
                yield StreamEvent(
                    usage=Usage(
                        input_tokens=usage_input,
                        output_tokens=usage_output,
                        cache_write=cache_write,
                        cache_read=cache_read,
                    )
                )
                yield StreamEvent(done=True)
            except httpx.HTTPStatusError as exc:
                if _is_prompt_too_long(exc):
                    wrapped = PromptTooLongError("anthropic prompt too long")
                    wrapped.__cause__ = exc
                    yield StreamEvent(err=wrapped)
                    return
                raise ProviderError(self._format_http_error(exc)) from exc
            except httpx.RequestError as exc:
                raise ProviderError(
                    f"Anthropic request failed: {exc.__class__.__name__}"
                ) from exc

    def build_payload(self, request: Request) -> dict[str, Any]:
        """构造可独立测试的 Anthropic 请求体。"""
        messages_payload = self._build_messages_payload(request.messages)
        self._append_reminder(messages_payload, request.reminder)
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages_payload,
            "max_tokens": 4096,
            "stream": True,
        }
        system_blocks: list[dict[str, Any]] = []
        if request.system.stable:
            system_blocks.append(
                {
                    "type": "text",
                    "text": request.system.stable,
                    "cache_control": {"type": "ephemeral"},
                }
            )
        if request.system.environment:
            system_blocks.append({"type": "text", "text": request.system.environment})
        if system_blocks:
            payload["system"] = system_blocks
        if request.tools:
            payload["tools"] = [self._tool_definition(tool) for tool in request.tools]
        if self._thinking and not self._history_has_tools(request.messages):
            payload["thinking"] = {"type": "enabled", "budget_tokens": 1024}
        return payload

    def _build_messages_payload(self, messages: list[Message]) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                payload.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": result.tool_call_id,
                                "content": result.content,
                                "is_error": result.is_error,
                            }
                            for result in message.tool_results
                        ],
                    }
                )
            elif message.role == "assistant" and message.tool_calls:
                content: list[dict[str, Any]] = []
                if message.content:
                    content.append({"type": "text", "text": message.content})
                for call in message.tool_calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": call.id,
                            "name": call.name,
                            "input": self._json_object(call.input),
                        }
                    )
                payload.append({"role": "assistant", "content": content})
            elif message.role in ("user", "assistant"):
                payload.append({"role": message.role, "content": message.content})
        return payload

    @staticmethod
    def _append_reminder(messages: list[dict[str, Any]], reminder: str) -> None:
        """把动态 reminder 编织进请求副本，不修改 Session。"""
        if not reminder:
            return
        block = {"type": "text", "text": reminder}
        if messages and messages[-1].get("role") == "user":
            content = messages[-1].get("content")
            if isinstance(content, list):
                content.append(block)
            else:
                messages[-1]["content"] = [
                    {"type": "text", "text": str(content or "")},
                    block,
                ]
            return
        messages.append({"role": "user", "content": [block]})

    @staticmethod
    def _parse_start_usage(usage: Any) -> tuple[int, int, int]:
        """解析 Anthropic message_start 用量，缺字段按零。"""
        if not isinstance(usage, dict):
            return 0, 0, 0
        return (
            usage.get("input_tokens", 0) or 0,
            usage.get("cache_creation_input_tokens", 0) or 0,
            usage.get("cache_read_input_tokens", 0) or 0,
        )

    @staticmethod
    def _parse_output_usage(usage: Any) -> int:
        """解析 Anthropic message_delta 输出用量。"""
        return (usage.get("output_tokens", 0) or 0) if isinstance(usage, dict) else 0

    @staticmethod
    def _parse_start_usage(usage: Any) -> tuple[int, int, int]:
        """解析 Anthropic message_start 用量，缺字段按零。"""
        if not isinstance(usage, dict):
            return 0, 0, 0
        return (
            usage.get("input_tokens", 0) or 0,
            usage.get("cache_creation_input_tokens", 0) or 0,
            usage.get("cache_read_input_tokens", 0) or 0,
        )

    @staticmethod
    def _parse_output_usage(usage: Any) -> int:
        """解析 Anthropic message_delta 输出用量。"""
        return (usage.get("output_tokens", 0) or 0) if isinstance(usage, dict) else 0

    @staticmethod
    def _handle_block_start(
        data: dict[str, Any], tool_blocks: dict[int, dict[str, str]]
    ) -> None:
        block = data.get("content_block") or {}
        if block.get("type") != "tool_use":
            return
        index = int(data.get("index", len(tool_blocks)))
        tool_blocks[index] = {
            "id": block.get("id") or f"toolu_{index}",
            "name": block.get("name") or "",
            "args": json.dumps(block.get("input") or {}, ensure_ascii=False)
            if block.get("input")
            else "",
        }

    @staticmethod
    def _handle_block_delta(
        data: dict[str, Any], tool_blocks: dict[int, dict[str, str]]
    ) -> StreamEvent | None:
        delta = data.get("delta") or {}
        delta_type = delta.get("type")
        if delta_type == "text_delta":
            token = delta.get("text") or ""
            return StreamEvent(text=token) if token else None
        if delta_type == "input_json_delta":
            index = int(data.get("index", 0))
            buffer = tool_blocks.setdefault(
                index, {"id": f"toolu_{index}", "name": "", "args": ""}
            )
            buffer["args"] = buffer.get("args", "") + (delta.get("partial_json") or "")
        return None

    @staticmethod
    def _build_tool_calls(tool_blocks: dict[int, dict[str, str]]) -> list[ToolCall]:
        return [
            ToolCall(
                id=tool_blocks[index].get("id") or f"toolu_{index}",
                name=tool_blocks[index].get("name") or "",
                input=tool_blocks[index].get("args") or "{}",
            )
            for index in sorted(tool_blocks)
        ]

    @staticmethod
    def _tool_definition(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }

    @staticmethod
    def _json_object(raw: str) -> dict[str, Any]:
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _history_has_tools(messages: list[Message]) -> bool:
        return any(message.tool_calls or message.tool_results for message in messages)

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        """Create an SSL context that trusts system CAs."""
        return ssl.create_default_context()

    @staticmethod
    def _format_http_error(exc: httpx.HTTPStatusError) -> str:
        body = exc.response.text.strip().replace("\n", " ")[:500]
        if body:
            return f"Anthropic API error {exc.response.status_code}: {body}"
        return f"Anthropic API error {exc.response.status_code}"


def _is_prompt_too_long(exc: httpx.HTTPStatusError) -> bool:
    text = exc.response.text.lower()
    return exc.response.status_code == 400 and (
        "prompt is too long" in text
        or "prompt_too_long" in text
        or "context_length" in text
    )
