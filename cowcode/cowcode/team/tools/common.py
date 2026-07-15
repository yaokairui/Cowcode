"""Team 工具公共辅助。"""

from __future__ import annotations

import json
from typing import Any

from cowcode.agent_team import teammate_context_from_ctx
from cowcode.team.tasks import Patch, Status, Task
from cowcode.tool import Result


def parse_args(args: str) -> dict[str, Any]:
    try:
        data = json.loads(args or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def as_json(value: Any) -> Result:
    return Result(json.dumps(value, ensure_ascii=False))


def team_from_ctx(manager, ctx: Any = None, explicit: str = ""):
    if explicit:
        team = manager.get(explicit)
        if team is not None:
            return team
    tc = teammate_context_from_ctx(ctx)
    if tc is not None:
        team = manager.get(tc.team_name)
        if team is not None:
            return team
    teams = manager.list_()
    return teams[0] if teams else None


def status_from_value(value: object) -> Status | None:
    if value in (None, ""):
        return None
    return Status(str(value))


def task_from_args(data: dict[str, Any]) -> Task:
    return Task(
        title=str(data.get("title", "") or ""),
        description=str(data.get("description", "") or ""),
        assignee=str(data.get("assignee", "") or ""),
        blocked_by=[str(x) for x in data.get("blocked_by", []) if x],
    )


def patch_from_args(data: dict[str, Any]) -> Patch:
    return Patch(
        title=str(data["title"]) if "title" in data else None,
        description=str(data["description"]) if "description" in data else None,
        status=status_from_value(data.get("status")),
        assignee=str(data["assignee"]) if "assignee" in data else None,
        add_blocks=[str(x) for x in data.get("add_blocks", []) if x],
        add_blocked_by=[str(x) for x in data.get("add_blocked_by", []) if x],
        remove_blocks=[str(x) for x in data.get("remove_blocks", []) if x],
        remove_blocked_by=[str(x) for x in data.get("remove_blocked_by", []) if x],
    )
