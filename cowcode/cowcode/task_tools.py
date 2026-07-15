"""Tools for inspecting and controlling background SubAgent tasks."""

from __future__ import annotations

import json
from dataclasses import asdict

from cowcode.task_manager import BackgroundTask, Manager, Status, TaskBusy, TaskNotFound
from cowcode.tool import Result


class TaskListTool:
    def __init__(self, manager: Manager) -> None:
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
        return "List background SubAgent tasks."

    def parameters(self) -> dict:
        return {"type": "object", "properties": {}}

    async def execute(self, args: str) -> Result:
        rows = [
            {
                "id": task.id,
                "name": task.name,
                "status": str(task.status),
                "tool_count": task.tool_count,
                "last_activity": task.last_activity,
            }
            for task in self._manager.list()
        ]
        return Result(json.dumps(rows, ensure_ascii=False))


class TaskGetTool:
    def __init__(self, manager: Manager) -> None:
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
        return "Get full status for one background SubAgent task."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        }

    async def execute(self, args: str) -> Result:
        data = _parse(args)
        task = self._manager.get(str(data.get("task_id", "")))
        if task is None:
            return Result("task not found", is_error=True)
        return Result(json.dumps(_task_payload(task), ensure_ascii=False))


class TaskStopTool:
    def __init__(self, manager: Manager) -> None:
        self._manager = manager

    @property
    def read_only(self) -> bool:
        return False

    @property
    def is_system(self) -> bool:
        return True

    def name(self) -> str:
        return "TaskStop"

    def description(self) -> str:
        return "Cancel a running background SubAgent task."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        }

    async def execute(self, args: str) -> Result:
        data = _parse(args)
        ok = await self._manager.stop(str(data.get("task_id", "")))
        if not ok:
            return Result("task not found", is_error=True)
        return Result(json.dumps({"status": "cancellation_requested"}))


class SendMessageTool:
    def __init__(self, manager: Manager) -> None:
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
        return "Send a follow-up message to a completed named background SubAgent."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["name", "message"],
        }

    async def execute(self, args: str) -> Result:
        data = _parse(args)
        try:
            task_id = await self._manager.send_message(
                str(data.get("name", "")), str(data.get("message", ""))
            )
        except TaskNotFound as exc:
            return Result(f"task name not found: {exc}", is_error=True)
        except TaskBusy as exc:
            return Result(f"task is busy: {exc}", is_error=True)
        return Result(json.dumps({"task_id": task_id, "status": "resumed"}))


def _parse(args: str) -> dict:
    try:
        data = json.loads(args or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _task_payload(task: BackgroundTask) -> dict:
    return {
        "id": task.id,
        "name": task.name,
        "status": str(task.status),
        "task": task.task,
        "result": task.result,
        "err": str(task.err) if task.err else "",
        "start_time": task.start_time,
        "end_time": task.end_time,
        "usage": asdict(task.usage),
        "tool_count": task.tool_count,
        "last_activity": task.last_activity,
    }
