"""Team 工具集合。"""

from __future__ import annotations

import time

from cowcode.task_manager import Status as BgStatus, TaskBusy, TaskNotFound
from cowcode.team.backend import new_backend
from cowcode.team.mailbox import Box, Message, MessageType
from cowcode.team.tasks import Filter, Store
from cowcode.team.tools.common import (
    as_json,
    parse_args,
    patch_from_args,
    status_from_value,
    task_from_args,
    team_from_ctx,
)
from cowcode.tool import Result


class TeamCreateTool:
    def __init__(self, manager) -> None:
        self._manager = manager

    @property
    def read_only(self) -> bool:
        return False

    @property
    def is_system(self) -> bool:
        return True

    def name(self) -> str:
        return "TeamCreate"

    def description(self) -> str:
        return "Create a persistent agent team."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"team_name": {"type": "string"}, "description": {"type": "string"}},
            "required": ["team_name"],
        }

    async def execute(self, args: str) -> Result:
        data = parse_args(args)
        team = await self._manager.create(str(data.get("team_name", "")), str(data.get("description", "") or ""))
        return as_json({"team_name": team.sanitized_name, "backend": str(team.backend), "config_path": team.config_path})


class TeamDeleteTool:
    def __init__(self, manager) -> None:
        self._manager = manager

    @property
    def read_only(self) -> bool:
        return False

    @property
    def is_system(self) -> bool:
        return True

    def name(self) -> str:
        return "TeamDelete"

    def description(self) -> str:
        return "Delete a persistent agent team."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"team_name": {"type": "string"}, "force": {"type": "boolean"}},
            "required": ["team_name"],
        }

    async def execute(self, args: str) -> Result:
        data = parse_args(args)
        await self._manager.delete(str(data.get("team_name", "")), bool(data.get("force", False)))
        return as_json({"status": "deleted"})


class TeamTaskCreateTool:
    def __init__(self, manager) -> None:
        self._manager = manager

    @property
    def read_only(self) -> bool:
        return False

    @property
    def is_system(self) -> bool:
        return True

    def name(self) -> str:
        return "TaskCreate"

    def description(self) -> str:
        return "Create a shared team task."

    def parameters(self) -> dict:
        return {"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}, "assignee": {"type": "string"}, "blocked_by": {"type": "array", "items": {"type": "string"}}}, "required": ["title"]}

    async def execute(self, args: str) -> Result:
        data = parse_args(args)
        team = team_from_ctx(self._manager, explicit=str(data.get("team_name", "") or ""))
        if team is None:
            return Result("team not found", is_error=True)
        store = Store(team.tasks_path)
        task_id = await store.create(task_from_args(data))
        return as_json({"task_id": task_id})


class TeamTaskGetTool:
    def __init__(self, manager) -> None:
        self._manager = manager

    @property
    def read_only(self) -> bool:
        return True

    @property
    def is_system(self) -> bool:
        return True

    def name(self) -> str:
        return "TaskGet"

    def description(self) -> str:
        return "Get a shared team task."

    def parameters(self) -> dict:
        return {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}

    async def execute(self, args: str) -> Result:
        data = parse_args(args)
        team = team_from_ctx(self._manager, explicit=str(data.get("team_name", "") or ""))
        if team is None:
            return Result("team not found", is_error=True)
        try:
            task = await Store(team.tasks_path).get(str(data.get("task_id", "")))
        except KeyError:
            return Result("task not found", is_error=True)
        return as_json(task.to_dict(include_ready=True))


class TeamTaskListTool:
    def __init__(self, manager) -> None:
        self._manager = manager

    @property
    def read_only(self) -> bool:
        return True

    @property
    def is_system(self) -> bool:
        return True

    def name(self) -> str:
        return "TaskList"

    def description(self) -> str:
        return "List shared team tasks."

    def parameters(self) -> dict:
        return {"type": "object", "properties": {"status": {"type": "string"}}}

    async def execute(self, args: str) -> Result:
        data = parse_args(args)
        team = team_from_ctx(self._manager, explicit=str(data.get("team_name", "") or ""))
        if team is None:
            return Result("team not found", is_error=True)
        tasks = await Store(team.tasks_path).list_(Filter(status_from_value(data.get("status"))))
        return as_json([task.to_dict(include_ready=True) for task in tasks])


class TeamTaskUpdateTool:
    def __init__(self, manager) -> None:
        self._manager = manager

    @property
    def read_only(self) -> bool:
        return False

    @property
    def is_system(self) -> bool:
        return True

    def name(self) -> str:
        return "TaskUpdate"

    def description(self) -> str:
        return "Update a shared team task."

    def parameters(self) -> dict:
        return {"type": "object", "properties": {"task_id": {"type": "string"}}, "required": ["task_id"]}

    async def execute(self, args: str) -> Result:
        data = parse_args(args)
        team = team_from_ctx(self._manager, explicit=str(data.get("team_name", "") or ""))
        if team is None:
            return Result("team not found", is_error=True)
        await Store(team.tasks_path).update(str(data.get("task_id", "")), patch_from_args(data))
        return as_json({"status": "updated"})


class TeamSendMessageTool:
    def __init__(self, manager) -> None:
        self._manager = manager

    @property
    def read_only(self) -> bool:
        return False

    @property
    def is_system(self) -> bool:
        return True

    def name(self) -> str:
        return "SendMessage"

    def description(self) -> str:
        return "Send a message to a teammate."

    def parameters(self) -> dict:
        return {"type": "object", "properties": {"to": {"type": "string"}, "summary": {"type": "string"}, "message": {"type": "string"}, "type": {"type": "string"}, "payload": {"type": "object"}}, "required": ["to"]}

    async def execute(self, args: str) -> Result:
        data = parse_args(args)
        team = team_from_ctx(self._manager, explicit=str(data.get("team_name", "") or ""))
        if team is None:
            return Result("team not found", is_error=True)
        sender = str(data.get("from", "lead") or "lead")
        targets = self._resolve_targets(team, str(data.get("to", "")))
        if not targets:
            return Result("target not found", is_error=True)
        delivered: list[str] = []
        now = int(time.time())
        box = Box(team.mailbox_dir)
        for member in targets:
            msg = Message(
                from_=sender,
                to=member.agent_id,
                type=MessageType(str(data.get("type") or MessageType.TEXT)),
                summary=str(data.get("summary", "") or "message"),
                content=str(data.get("message", "") or data.get("content", "") or ""),
                payload=data.get("payload") if isinstance(data.get("payload"), dict) else None,
                timestamp=now,
            )
            await box.write(member.agent_id, msg)
            backend = new_backend(member.backend_type, task_mgr=self._manager.task_mgr)
            await backend.wake(member.pane_id, member.agent_id)
            if member.backend_type.value == "in-process" and self._manager.task_mgr is not None:
                task = self._manager.task_mgr.get(member.agent_id)
                if task is not None and task.status != BgStatus.RUNNING:
                    await self._manager.set_member_active(team, member.name, True)
                    try:
                        await self._manager.task_mgr.send_message(member.name, msg.content)
                    except (TaskBusy, TaskNotFound):
                        pass
            delivered.append(member.agent_id)
        return as_json({"delivered_to": delivered, "timestamp": now})

    def _resolve_targets(self, team, to: str):
        if to == "*":
            return [member for member in team.members if member.agent_id != "lead"]
        agent_id = self._manager.registry.resolve(to) or to
        return [
            member
            for member in team.members
            if member.name == to or member.agent_id == agent_id
        ]


def register_team_tools(registry, manager) -> None:
    registry.register(TeamCreateTool(manager))
    registry.register(TeamDeleteTool(manager))
    registry.register(TeamTaskCreateTool(manager))
    registry.register(TeamTaskGetTool(manager))
    registry.register(TeamTaskListTool(manager))
    registry.register(TeamTaskUpdateTool(manager))
    registry.register(TeamSendMessageTool(manager))
