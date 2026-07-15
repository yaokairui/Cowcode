from __future__ import annotations

import json

import pytest

from cowcode.team import BackendType, Manager, TeammateInfo
from cowcode.team.registry import AgentNameRegistry
from cowcode.team.tools import register_team_tools
from cowcode.tool import Registry


@pytest.mark.asyncio
async def test_team_tools_register_and_send_message(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cowcode.team.manager.detect", lambda: BackendType.IN_PROCESS)
    mgr = Manager(tmp_path, tmp_path, None, None, AgentNameRegistry())
    team = await mgr.create("demo", "")
    await team.add_member(
        TeammateInfo(name="alice", agent_id="agent-123", is_active=False)
    )
    mgr.registry.register("alice", "agent-123")

    registry = Registry()
    register_team_tools(registry, mgr)
    names = {definition.name for definition in registry.definitions()}
    assert {
        "TeamCreate",
        "TeamDelete",
        "TaskCreate",
        "TaskGet",
        "TaskList",
        "TaskUpdate",
        "SendMessage",
    }.issubset(names)

    send = registry.get("SendMessage")
    assert send is not None
    result = await send.execute(
        json.dumps({"to": "alice", "summary": "ping now", "message": "hello"})
    )
    assert not result.is_error
    payload = json.loads(result.content)
    assert payload["delivered_to"] == ["agent-123"]

    from cowcode.team.mailbox import Box

    messages = await Box(team.mailbox_dir).read("agent-123")
    assert messages[0].content == "hello"


@pytest.mark.asyncio
async def test_team_task_tools(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cowcode.team.manager.detect", lambda: BackendType.IN_PROCESS)
    mgr = Manager(tmp_path, tmp_path, None, None, AgentNameRegistry())
    team = await mgr.create("demo", "")
    registry = Registry()
    register_team_tools(registry, mgr)

    create = registry.get("TaskCreate")
    update = registry.get("TaskUpdate")
    list_tool = registry.get("TaskList")
    assert create and update and list_tool

    r1 = await create.execute(
        json.dumps({"team_name": team.sanitized_name, "title": "one"})
    )
    r2 = await create.execute(
        json.dumps({"team_name": team.sanitized_name, "title": "two"})
    )
    one = json.loads(r1.content)["task_id"]
    two = json.loads(r2.content)["task_id"]
    await update.execute(
        json.dumps(
            {"team_name": team.sanitized_name, "task_id": two, "add_blocked_by": [one]}
        )
    )
    listed = json.loads(
        (
            await list_tool.execute(
                json.dumps({"team_name": team.sanitized_name, "status": "pending"})
            )
        ).content
    )
    by_id = {item["id"]: item for item in listed}
    assert by_id[two]["blocked_by"] == [one]
    assert by_id[two]["is_ready"] is False
