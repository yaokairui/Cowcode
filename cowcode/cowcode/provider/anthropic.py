"""Anthropic Claude provider for Cowcode."""

from __future__ import annotations

import json
import ssl
from typing import Any, AsyncIterator

import httpx

from cowcode.config import ProviderConfig
from cowcode.provider.base import Provider, ProviderError
from cowcode.session import Message, Session, StreamEvent, ToolCall, ToolDefinition

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

    async def stream(
        self, session: Session, tools: list[ToolDefinition] | None = None
    ) -> AsyncIterator[StreamEvent]:
        """Stream visible text and tool-call events from Claude."""
        messages = session.get_history()
        system_text, messages_payload = self._build_messages_payload(messages)

        url = self._base_url + self.STREAM_URL
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages_payload,
            "max_tokens": 4096,
            "stream": True,
        }
        if system_text:
            payload["system"] = system_text
        if tools:
            payload["tools"] = [self._tool_definition(tool) for tool in tools]
        if self._thinking and not self._history_has_tools(messages):
            payload["thinking"] = {"type": "enabled", "budget_tokens": 1024}

        tool_blocks: dict[int, dict[str, str]] = {}
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

                        if event_name == "content_block_start":
                            self._handle_block_start(data, tool_blocks)
                        elif event_name == "content_block_delta":
                            event = self._handle_block_delta(data, tool_blocks)
                            if event is not None:
                                yield event

                if tool_blocks:
                    yield StreamEvent(tool_calls=self._build_tool_calls(tool_blocks))
                yield StreamEvent(done=True)
            except httpx.HTTPStatusError as exc:
                raise ProviderError(self._format_http_error(exc)) from exc
            except httpx.RequestError as exc:
                raise ProviderError(
                    f"Anthropic request failed: {exc.__class__.__name__}"
                ) from exc

    def _build_messages_payload(
        self, messages: list[Message]
    ) -> tuple[str, list[dict[str, Any]]]:
        system_text = ""
        payload: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                system_text = message.content
            elif message.role == "tool":
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
        return system_text, payload

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
            buffer = tool_blocks.setdefault(index, {"id": f"toolu_{index}", "name": "", "args": ""})
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
