"""Conversation API compatible with the ch02 task list."""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable

from cowcode.session import Message

__all__ = ["Conversation"]


class Conversation:
    """Simple multi-turn conversation history."""

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
    ) -> "Conversation":
        conv = cls(on_append=on_append, on_replace=on_replace)
        with conv._lock:
            conv._messages = copy.deepcopy(msgs)
        return conv

    def add_user(self, text: str) -> None:
        msg = Message(role="user", content=text)
        with self._lock:
            self._messages.append(msg)
        if self._on_append is not None:
            self._on_append(copy.deepcopy(msg))

    def add_assistant(self, text: str) -> None:
        msg = Message(role="assistant", content=text)
        with self._lock:
            self._messages.append(msg)
        if self._on_append is not None:
            self._on_append(copy.deepcopy(msg))

    def replace_messages(self, msgs: list[Message] | None) -> None:
        with self._lock:
            self._messages = copy.deepcopy(msgs or [])
            replaced = copy.deepcopy(self._messages)
        if self._on_replace is not None:
            self._on_replace(replaced)

    def messages(self) -> list[Message]:
        with self._lock:
            return copy.deepcopy(self._messages)

    def __len__(self) -> int:
        with self._lock:
            return len(self._messages)
