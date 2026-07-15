"""Team 共享任务列表。"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from cowcode.team.filelock import acquire
from cowcode.team.persistence import atomic_write_json, read_json


class Status(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class Task:
    id: str = ""
    title: str = ""
    description: str = ""
    status: Status = Status.PENDING
    assignee: str = ""
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    created_at: int = 0
    updated_at: int = 0
    is_ready: bool = True

    def to_dict(self, include_ready: bool = False) -> dict[str, Any]:
        data = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": str(self.status),
            "assignee": self.assignee,
            "blocked_by": list(self.blocked_by),
            "blocks": list(self.blocks),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_ready:
            data["is_ready"] = self.is_ready
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "") or ""),
            description=str(data.get("description", "") or ""),
            status=Status(str(data.get("status") or Status.PENDING)),
            assignee=str(data.get("assignee", "") or ""),
            blocked_by=[str(x) for x in data.get("blocked_by", [])],
            blocks=[str(x) for x in data.get("blocks", [])],
            created_at=int(data.get("created_at", 0) or 0),
            updated_at=int(data.get("updated_at", 0) or 0),
        )


@dataclass
class Filter:
    status: Status | None = None


@dataclass
class Patch:
    title: str | None = None
    description: str | None = None
    status: Status | None = None
    assignee: str | None = None
    add_blocks: list[str] = field(default_factory=list)
    add_blocked_by: list[str] = field(default_factory=list)
    remove_blocks: list[str] = field(default_factory=list)
    remove_blocked_by: list[str] = field(default_factory=list)


class Store:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def create(self, t: Task) -> str:
        async with acquire(self._lock_path()):
            tasks = self._read_tasks()
            now = int(time.time())
            t.id = t.id or self._next_id(tasks)
            t.created_at = t.created_at or now
            t.updated_at = now
            tasks.append(t)
            self._write_tasks(tasks)
            return t.id

    async def get(self, id_: str) -> Task:
        async with acquire(self._lock_path()):
            for task in self._read_tasks():
                if task.id == id_:
                    return self._with_ready(task, self._read_tasks())
        raise KeyError(id_)

    async def list_(self, filter_: Filter | None = None) -> list[Task]:
        async with acquire(self._lock_path()):
            tasks = self._read_tasks()
            result = tasks
            if filter_ is not None and filter_.status is not None:
                result = [task for task in result if task.status == filter_.status]
            return [self._with_ready(task, tasks) for task in result]

    async def update(self, id_: str, patch: Patch) -> None:
        async with acquire(self._lock_path()):
            tasks = self._read_tasks()
            by_id = {task.id: task for task in tasks}
            task = by_id.get(id_)
            if task is None:
                raise KeyError(id_)
            if patch.title is not None:
                task.title = patch.title
            if patch.description is not None:
                task.description = patch.description
            if patch.status is not None:
                task.status = patch.status
            if patch.assignee is not None:
                task.assignee = patch.assignee
            self._add_many(task.blocks, patch.add_blocks)
            self._add_many(task.blocked_by, patch.add_blocked_by)
            self._remove_many(task.blocks, patch.remove_blocks)
            self._remove_many(task.blocked_by, patch.remove_blocked_by)
            for other_id in patch.add_blocked_by:
                other = by_id.get(other_id)
                if other is not None:
                    self._add_many(other.blocks, [task.id])
            for other_id in patch.add_blocks:
                other = by_id.get(other_id)
                if other is not None:
                    self._add_many(other.blocked_by, [task.id])
            for other_id in patch.remove_blocked_by:
                other = by_id.get(other_id)
                if other is not None:
                    self._remove_many(other.blocks, [task.id])
            for other_id in patch.remove_blocks:
                other = by_id.get(other_id)
                if other is not None:
                    self._remove_many(other.blocked_by, [task.id])
            task.updated_at = int(time.time())
            self._write_tasks(tasks)

    def _lock_path(self) -> Path:
        return self._path.with_name(self._path.name + ".lock")

    def _read_tasks(self) -> list[Task]:
        try:
            data = read_json(self._path)
        except FileNotFoundError:
            return []
        items = data.get("tasks", []) if isinstance(data, dict) else []
        return [Task.from_dict(item) for item in items if isinstance(item, dict)]

    def _write_tasks(self, tasks: list[Task]) -> None:
        atomic_write_json(self._path, {"tasks": [task.to_dict() for task in tasks]})

    @staticmethod
    def _next_id(existing: list[Task]) -> str:
        used = {task.id for task in existing}
        while True:
            value = "task_" + secrets.token_hex(3)
            if value not in used:
                return value

    @staticmethod
    def _with_ready(task: Task, tasks: list[Task]) -> Task:
        statuses = {item.id: item.status for item in tasks}
        task.is_ready = all(
            statuses.get(dep) == Status.COMPLETED for dep in task.blocked_by
        )
        return task

    @staticmethod
    def _add_many(target: list[str], values: list[str]) -> None:
        for value in values:
            if value and value not in target:
                target.append(value)

    @staticmethod
    def _remove_many(target: list[str], values: list[str]) -> None:
        for value in values:
            while value in target:
                target.remove(value)
