"""Conversation session management for Cowcode."""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

_LOG = logging.getLogger(__name__)

__all__ = [
    "Message",
    "Session",
    "StreamEvent",
    "ToolCall",
    "ToolDefinition",
    "ToolResult",
    "Usage",
    "Entry",
    "SessionInfo",
    "Writer",
    "clean_expired",
    "last_message_ts",
    "list_sessions",
    "load_session",
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

    def __init__(
        self,
        on_append: Callable[[Message], None] | None = None,
        on_replace: Callable[[list[Message]], None] | None = None,
    ) -> None:
        self._messages: list[Message] = []
        self._lock = threading.RLock()
        self._on_append = on_append
        self._on_replace = on_replace

    @classmethod
    def from_messages(
        cls,
        msgs: list[Message],
        on_append: Callable[[Message], None] | None = None,
        on_replace: Callable[[list[Message]], None] | None = None,
    ) -> "Session":
        session = cls(on_append=on_append, on_replace=on_replace)
        with session._lock:
            session._messages = copy.deepcopy(msgs)
        return session

    def append(self, role: str, content: str) -> None:
        """Add a plain message to the conversation history."""

        msg = Message(role=role, content=content)
        with self._lock:
            self._messages.append(msg)
        self._notify_append(msg)

    def add_assistant_with_tool_calls(
        self, content: str, tool_calls: list[ToolCall]
    ) -> None:
        """追加 assistant 发起工具调用的回合。"""

        with self._lock:
            msg = Message(
                role="assistant", content=content, tool_calls=list(tool_calls)
            )
            self._messages.append(msg)
        self._notify_append(msg)

    def add_tool_results(self, results: list[ToolResult]) -> None:
        """追加工具执行结果回合。"""

        with self._lock:
            msg = Message(role="tool", tool_results=list(results))
            self._messages.append(msg)
        self._notify_append(msg)

    def add_system_prompt(self, text: str) -> None:
        """Add the system prompt as the first message."""

        if text and self.is_empty:
            self.append("system", text)

    def replace_messages(self, msgs: list[Message] | None) -> None:
        """整体替换历史，深拷贝入参。"""

        with self._lock:
            self._messages = copy.deepcopy(msgs or [])
            replaced = copy.deepcopy(self._messages)
        if self._on_replace is not None:
            self._on_replace(replaced)

    def _notify_append(self, msg: Message) -> None:
        if self._on_append is not None:
            self._on_append(copy.deepcopy(msg))

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


@dataclass
class Entry:
    role: str = ""
    content: str = ""
    tool_calls: list[dict[str, Any]] | None = None
    tool_results: list[dict[str, Any]] | None = None
    ts: int = 0
    model: str | None = None
    type: str | None = None


@dataclass
class SessionInfo:
    id: str
    title: str
    modified_at: datetime
    model: str
    size: int
    dir: str


class Writer:
    """向 conversation.jsonl 追加写入。"""

    def __init__(self, session_dir: str, create: bool = True) -> None:
        self.session_dir = session_dir
        self.path = Path(session_dir) / "conversation.jsonl"
        if create:
            Path(session_dir).mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("ab")
        self._lock = threading.Lock()
        self._wrote_first = self.path.stat().st_size > 0
        self._model = ""

    @classmethod
    def open_existing(cls, session_dir: str) -> "Writer":
        return cls(session_dir, create=False)

    def bind_model(self, model: str) -> None:
        self._model = model

    def on_append(self, msg: Message) -> None:
        self.append(msg, self._model, not self._wrote_first)

    def on_replace(self, msgs: list[Message]) -> None:
        self.write_compact_marker()
        self.append_all(msgs)

    def append(self, msg: Message, model: str = "", is_first: bool = False) -> None:
        entry = Entry(
            role=msg.role,
            content=msg.content,
            tool_calls=[asdict(call) for call in msg.tool_calls] or None,
            tool_results=[asdict(result) for result in msg.tool_results] or None,
            ts=int(time.time()),
            model=model if is_first and model else None,
        )
        self._write_entry(asdict(entry))
        self._wrote_first = True

    def write_compact_marker(self) -> None:
        self._write_entry({"type": "compact", "ts": int(time.time())})

    def append_all(self, msgs: list[Message]) -> None:
        for msg in msgs:
            self.append(msg, "", False)

    def close(self) -> None:
        with self._lock:
            self._file.close()

    def _write_entry(self, data: dict[str, Any]) -> None:
        cleaned = {
            key: value for key, value in data.items() if value not in (None, [], "")
        }
        line = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            self._file.write(line.encode("utf-8"))
            self._file.flush()
            os.fsync(self._file.fileno())

    def __enter__(self) -> "Writer":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _session_time(session_id: str) -> datetime:
    return datetime.strptime(session_id[:15], "%Y%m%d-%H%M%S")


def list_sessions(sessions_dir: str) -> list[SessionInfo]:
    root = Path(sessions_dir)
    if not root.is_dir():
        return []
    items: list[SessionInfo] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            _session_time(child.name)
        except ValueError:
            continue
        jsonl = child / "conversation.jsonl"
        if not jsonl.exists():
            continue
        stat = jsonl.stat()
        title = "(untitled)"
        model = ""
        try:
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not model and isinstance(data.get("model"), str):
                    model = data["model"]
                if data.get("role") == "user":
                    content = str(data.get("content", ""))
                    title = content[:47] + "..." if len(content) > 50 else content
                    break
        except OSError:
            continue
        items.append(
            SessionInfo(
                id=child.name,
                title=title,
                modified_at=datetime.fromtimestamp(stat.st_mtime),
                model=model,
                size=stat.st_size,
                dir=str(child),
            )
        )
    return sorted(items, key=lambda item: item.modified_at, reverse=True)


def load_session(session_dir: str) -> list[Message]:
    path = Path(session_dir) / "conversation.jsonl"
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    last_compact = -1
    for index, line in enumerate(lines):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append(data)
        if data.get("type") == "compact":
            last_compact = len(rows) - 1
    msgs = [
        _message_from_dict(data)
        for data in rows[last_compact + 1 :]
        if data.get("role")
    ]
    return _truncate_orphaned_tool_calls([msg for msg in msgs if msg is not None])


def _message_from_dict(data: dict[str, Any]) -> Message | None:
    role = data.get("role")
    if not isinstance(role, str):
        return None
    calls = [
        ToolCall(**item)
        for item in data.get("tool_calls") or []
        if isinstance(item, dict)
    ]
    results = [
        ToolResult(**item)
        for item in data.get("tool_results") or []
        if isinstance(item, dict)
    ]
    return Message(
        role=role,
        content=str(data.get("content", "") or ""),
        tool_calls=calls,
        tool_results=results,
    )


def _truncate_orphaned_tool_calls(msgs: list[Message]) -> list[Message]:
    if msgs and msgs[-1].role == "assistant" and msgs[-1].tool_calls:
        return msgs[:-1]
    return msgs


def last_message_ts(session_dir: str) -> int | None:
    """返回 JSONL 中最后一条有效消息的写入时间。"""

    path = Path(session_dir) / "conversation.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    last_ts: int | None = None
    for line in lines:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not data.get("role"):
            continue
        ts = data.get("ts")
        if isinstance(ts, int):
            last_ts = ts
    return last_ts


def clean_expired(sessions_dir: str, max_age: timedelta) -> None:
    root = Path(sessions_dir)
    if not root.is_dir():
        return
    now = datetime.now()
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            created = _session_time(child.name)
        except ValueError:
            continue
        if now - created <= max_age:
            continue
        try:
            shutil.rmtree(child)
        except OSError as exc:
            _LOG.warning("清理过期会话失败 %s: %s", child, exc)
