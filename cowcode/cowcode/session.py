"""Conversation session management for Cowcode."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Message",
    "Session",
    "StreamEvent",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
    "Usage",
]


@dataclass
class Usage:
    """一轮请求的 token 用量。"""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write: int = 0
    cache_read: int = 0


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
    """Provider 流式事件。"""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    done: bool = False
    err: Exception | None = None


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
        self._lock = threading.RLock()

    def append(self, role: str, content: str) -> None:
        """Add a plain message to the conversation history."""

        with self._lock:
            self._messages.append(Message(role=role, content=content))

    def add_assistant_with_tool_calls(
        self, content: str, tool_calls: list[ToolCall]
    ) -> None:
        """追加 assistant 发起工具调用的回合。"""

        with self._lock:
            self._messages.append(
                Message(role="assistant", content=content, tool_calls=list(tool_calls))
            )

    def add_tool_results(self, results: list[ToolResult]) -> None:
        """追加工具执行结果回合。"""

        with self._lock:
            self._messages.append(Message(role="tool", tool_results=list(results)))

    def add_system_prompt(self, text: str) -> None:
        """Add the system prompt as the first message."""

        if text and self.is_empty:
            self.append("system", text)

    def replace_messages(self, msgs: list[Message] | None) -> None:
        """整体替换历史，深拷贝入参。"""

        with self._lock:
            self._messages = copy.deepcopy(msgs or [])

    def last_role(self) -> str:
        """返回最后一条消息的 role；空历史返回空字符串。"""

        with self._lock:
            return self._messages[-1].role if self._messages else ""

    def get_history(self) -> list[Message]:
        """Return a deep copy of the message history."""

        with self._lock:
            return copy.deepcopy(self._messages)

    def length(self) -> int:
        """返回当前消息数。"""

        with self._lock:
            return len(self._messages)

    @property
    def messages(self) -> list[Message]:
        """Return the message history (alias for get_history)."""

        return self.get_history()

    @property
    def is_empty(self) -> bool:
        """Check if the session has no messages yet."""

        return self.length() == 0

    @property
    def user_message_count(self) -> int:
        """Count how many user messages have been sent."""

        with self._lock:
            return sum(1 for m in self._messages if m.role == "user")
