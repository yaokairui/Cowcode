"""Team 邮箱文件读写。"""

from __future__ import annotations

import time
from pathlib import Path

from cowcode.team.filelock import acquire
from cowcode.team.mailbox.message import Message, MessageType
from cowcode.team.persistence import atomic_write_json, read_json

__all__ = ["Box", "Message", "MessageType"]


class Box:
    def __init__(self, dir_: str | Path) -> None:
        self._dir = Path(dir_)
        self._dir.mkdir(parents=True, exist_ok=True)

    async def write(self, agent_id: str, msg: Message) -> None:
        path = self._path(agent_id)
        async with acquire(self._lock_path(agent_id)):
            data = self._read_data(path)
            if msg.timestamp == 0:
                msg.timestamp = int(time.time())
            data["messages"].append(msg.to_dict())
            atomic_write_json(path, data)

    async def read(self, agent_id: str) -> list[Message]:
        path = self._path(agent_id)
        async with acquire(self._lock_path(agent_id)):
            return self._messages(path)

    async def read_unread(self, agent_id: str) -> tuple[list[int], list[Message]]:
        path = self._path(agent_id)
        async with acquire(self._lock_path(agent_id)):
            messages = self._messages(path)
            indices = [index for index, msg in enumerate(messages) if not msg.read]
            return indices, [messages[index] for index in indices]

    async def mark_read(self, agent_id: str, indices: list[int]) -> None:
        path = self._path(agent_id)
        async with acquire(self._lock_path(agent_id)):
            data = self._read_data(path)
            messages = data["messages"]
            for index in indices:
                if 0 <= index < len(messages):
                    messages[index]["read"] = True
            atomic_write_json(path, data)

    def _path(self, agent_id: str) -> Path:
        return self._dir / f"{agent_id}.json"

    def _lock_path(self, agent_id: str) -> Path:
        return self._dir / f"{agent_id}.lock"

    @staticmethod
    def _read_data(path: Path) -> dict:
        try:
            data = read_json(path)
        except FileNotFoundError:
            return {"messages": []}
        if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
            return {"messages": []}
        return data

    @classmethod
    def _messages(cls, path: Path) -> list[Message]:
        data = cls._read_data(path)
        return [
            Message.from_dict(item) for item in data["messages"] if isinstance(item, dict)
        ]
