"""Conversation session management for Cowcode."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Message",
    "Session",
    "StreamEvent",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
]


@dataclass
class ToolCall:
    """协议无关的模型工具调用。"""

    id: str
    name: str
    input: str


@dataclass
class ToolResult:
    """协议无关的工具执行结果。"""

    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class ToolDefinition:
    """注册中心导出的工具定义。"""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class StreamEvent:
    """Provider 流式事件：文本增量、工具调用或完成标记。"""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    done: bool = False


@dataclass
class Message:
    """A single message in the conversation."""

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)


class Session:
    """Manages conversation history for a single Cowcode session."""

    def __init__(self) -> None:
        self._messages: list[Message] = []

    def append(self, role: str, content: str) -> None:
        """Add a plain message to the conversation history."""
        self._messages.append(Message(role=role, content=content))

    def add_assistant_with_tool_calls(
        self, content: str, tool_calls: list[ToolCall]
    ) -> None:
        """追加 assistant 发起工具调用的回合。"""
        self._messages.append(
            Message(role="assistant", content=content, tool_calls=list(tool_calls))
        )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        """追加工具执行结果回合。"""
        self._messages.append(Message(role="tool", tool_results=list(results)))

    def add_system_prompt(self, text: str) -> None:
        """Add the system prompt as the first message."""
        if text and self.is_empty:
            self.append("system", text)

    def get_history(self) -> list[Message]:
        """Return a shallow copy of the message history."""
        return list(self._messages)

    @property
    def messages(self) -> list[Message]:
        """Return the message history (alias for get_history)."""
        return self.get_history()

    @property
    def is_empty(self) -> bool:
        """Check if the session has no messages yet."""
        return len(self._messages) == 0

    @property
    def user_message_count(self) -> int:
        """Count how many user messages have been sent."""
        return sum(1 for m in self._messages if m.role == "user")
