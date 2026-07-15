from __future__ import annotations

import json

import pytest

from cowcode.agent import Agent
from cowcode.agent_tool import AgentTool
from cowcode.subagent import Catalog
from cowcode.task_manager import Manager as TaskManager
from cowcode.tool import Registry


class ParentProvider:
    @property
    def model(self) -> str:
        return "fake"


class MockTeamHook:
    def __init__(self) -> None:
        self.called = None

    async def spawn_teammate(self, req) -> str:
        self.called = req
        return json.dumps({"ok": True})

    def is_teammate_context(self, ctx):
        return "", "", False


@pytest.mark.asyncio
async def test_agent_tool_team_name_delegates_to_hook() -> None:
    registry = Registry()
    task_mgr = TaskManager()
    hook = MockTeamHook()
    parent = Agent(ParentProvider(), registry)
    tool = AgentTool(
        Catalog(),
        task_mgr,
        registry,
        parent_getter=lambda: parent,
        messages_getter=lambda: [],
        team_hook=hook,
    )

    result = await tool.execute(
        json.dumps(
            {"prompt": "do", "description": "d", "team_name": "demo", "name": "alice"}
        )
    )
    assert not result.is_error
    assert hook.called is not None
    assert hook.called.team_name == "demo"
    assert hook.called.member_name == "alice"
