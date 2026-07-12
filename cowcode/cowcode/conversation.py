"""Conversation API compatible with the ch02 task list."""

from __future__ import annotations

import copy
import threading

from cowcode.session import Message

__all__ = ["Conversation"]


class Conversation:
    """Simple multi-turn conversation history."""

    def __init__(self) -> None:
        self._messages: list[Message] = []
        self._lock = threading.RLock()

    def add_user(self, text: str) -> None:
        with self._lock:
            self._messages.append(Message(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        with self._lock:
            self._messages.append(Message(role="assistant", content=text))

    def replace_messages(self, msgs: list[Message] | None) -> None:
        with self._lock:
            self._messages = copy.deepcopy(msgs or [])

    def messages(self) -> list[Message]:
        with self._lock:
            return copy.deepcopy(self._messages)

    def __len__(self) -> int:
        with self._lock:
            return len(self._messages)
