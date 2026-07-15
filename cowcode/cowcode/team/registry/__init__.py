"""Agent 名称注册表。"""

from __future__ import annotations

import threading


class AgentNameRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_name: dict[str, str] = {}
        self._by_id: dict[str, str] = {}

    def register(self, name: str, agent_id: str) -> None:
        if not name or not agent_id:
            return
        with self._lock:
            old_id = self._by_name.get(name)
            if old_id:
                self._by_id.pop(old_id, None)
            old_name = self._by_id.get(agent_id)
            if old_name:
                self._by_name.pop(old_name, None)
            self._by_name[name] = agent_id
            self._by_id[agent_id] = name

    def unregister(self, name: str) -> None:
        with self._lock:
            agent_id = self._by_name.pop(name, None)
            if agent_id:
                self._by_id.pop(agent_id, None)

    def unregister_by_agent_id(self, agent_id: str) -> None:
        with self._lock:
            name = self._by_id.pop(agent_id, None)
            if name:
                self._by_name.pop(name, None)

    def resolve(self, name_or_id: str) -> str | None:
        with self._lock:
            if name_or_id in self._by_name:
                return self._by_name[name_or_id]
            if name_or_id in self._by_id:
                return name_or_id
            return None

    def name_of(self, agent_id: str) -> str | None:
        with self._lock:
            return self._by_id.get(agent_id)

    def list_(self) -> dict[str, str]:
        with self._lock:
            return dict(self._by_name)
