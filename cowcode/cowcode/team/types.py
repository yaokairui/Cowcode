"""Team 数据类型。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class BackendType(StrEnum):
    TMUX = "tmux"
    ITERM2 = "iterm2"
    IN_PROCESS = "in-process"


class TeamError(Exception):
    """Team 模块基础异常。"""


class TeamNotFoundError(TeamError):
    pass


class TeamHasActiveMembersError(TeamError):
    pass


class MemberExistsError(TeamError):
    pass


class MemberNotFoundError(TeamError):
    pass


class InProcessTeammateNoSpawnError(TeamError):
    pass


@dataclass
class TeammateInfo:
    name: str
    agent_id: str
    agent_type: str = ""
    model: str = ""
    worktree_path: str = ""
    branch: str = ""
    backend_type: BackendType = BackendType.IN_PROCESS
    pane_id: str = ""
    is_active: bool | None = None
    plan_mode_required: bool = False
    session_dir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "agent_id": self.agent_id,
            "agent_type": self.agent_type,
            "model": self.model,
            "worktree_path": self.worktree_path,
            "branch": self.branch,
            "backend_type": str(self.backend_type),
            "pane_id": self.pane_id,
            "is_active": self.is_active,
            "plan_mode_required": self.plan_mode_required,
            "session_dir": self.session_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TeammateInfo":
        return cls(
            name=str(data.get("name", "")),
            agent_id=str(data.get("agent_id", "")),
            agent_type=str(data.get("agent_type", "") or ""),
            model=str(data.get("model", "") or ""),
            worktree_path=str(data.get("worktree_path", "") or ""),
            branch=str(data.get("branch", "") or ""),
            backend_type=BackendType(str(data.get("backend_type") or BackendType.IN_PROCESS)),
            pane_id=str(data.get("pane_id", "") or ""),
            is_active=data.get("is_active", None),
            plan_mode_required=bool(data.get("plan_mode_required", False)),
            session_dir=str(data.get("session_dir", "") or ""),
        )


@dataclass
class Team:
    name: str
    sanitized_name: str
    lead_agent_id: str
    backend: BackendType
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    members: list[TeammateInfo] = field(default_factory=list)
    config_dir: str = ""
    config_path: str = ""
    tasks_path: str = ""
    mailbox_dir: str = ""
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sanitized_name": self.sanitized_name,
            "lead_agent_id": self.lead_agent_id,
            "backend": str(self.backend),
            "description": self.description,
            "created_at": int(self.created_at.timestamp()),
            "members": [member.to_dict() for member in self.members],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Team":
        created = data.get("created_at")
        if isinstance(created, (int, float)):
            created_at = datetime.fromtimestamp(created)
        else:
            created_at = datetime.now()
        return cls(
            name=str(data.get("name", "")),
            sanitized_name=str(data.get("sanitized_name", "")),
            lead_agent_id=str(data.get("lead_agent_id", "lead") or "lead"),
            backend=BackendType(str(data.get("backend") or BackendType.IN_PROCESS)),
            description=str(data.get("description", "") or ""),
            created_at=created_at,
            members=[TeammateInfo.from_dict(item) for item in data.get("members", []) if isinstance(item, dict)],
        )

    async def add_member(self, info: TeammateInfo) -> None:
        from cowcode.team.persistence import atomic_write_json, reload_from_disk_locked

        async with self._lock:
            await reload_from_disk_locked(self)
            if any(member.name == info.name for member in self.members):
                raise MemberExistsError(info.name)
            self.members.append(info)
            atomic_write_json(self.config_path, self.to_dict())

    async def set_member_active(self, name: str, active: bool) -> None:
        from cowcode.team.persistence import atomic_write_json, reload_from_disk_locked

        async with self._lock:
            await reload_from_disk_locked(self)
            member = self.member_by_name(name)
            if member is None:
                raise MemberNotFoundError(name)
            member.is_active = active
            atomic_write_json(self.config_path, self.to_dict())

    async def remove_member(self, name: str) -> None:
        from cowcode.team.persistence import atomic_write_json, reload_from_disk_locked

        async with self._lock:
            await reload_from_disk_locked(self)
            before = len(self.members)
            self.members = [member for member in self.members if member.name != name]
            if len(self.members) == before:
                raise MemberNotFoundError(name)
            atomic_write_json(self.config_path, self.to_dict())

    def member_by_name(self, name: str) -> TeammateInfo | None:
        return next((member for member in self.members if member.name == name), None)

    def member_by_agent_id(self, agent_id: str) -> TeammateInfo | None:
        return next((member for member in self.members if member.agent_id == agent_id), None)
