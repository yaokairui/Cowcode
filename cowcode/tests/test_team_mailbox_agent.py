from __future__ import annotations

import pytest

from cowcode.agent import Agent
from cowcode.agent_team import IncomingMessage, TeammateContext
from cowcode.permission import Mode
from cowcode.session import Session, StreamEvent
from cowcode.tool import Registry


class CapturingProvider:
    def __init__(self) -> None:
        self.requests = []

    @property
    def model(self) -> str:
        return "fake"

    async def stream(self, request):
        self.requests.append(request)
        yield StreamEvent(text="done")
        yield StreamEvent(done=True)


@pytest.mark.asyncio
async def test_agent_injects_incoming_messages() -> None:
    provider = CapturingProvider()
    marked = []

    async def read_unread():
        return [0], [IncomingMessage(from_="lead", type="text", summary="hello there", content="body", timestamp=1)]

    async def mark_read(indices):
        marked.extend(indices)

    tc = TeammateContext("demo", "alice", "agent-1", read_unread=read_unread, mark_read=mark_read)
    session = Session()
    session.append("user", "hi")
    agent = Agent(provider, Registry(), ctx={"teammate": tc})
    events = [event async for event in agent.run(session, Mode.DEFAULT)]

    assert events[-1].done
    assert provider.requests
    assert "<incoming-messages>" in provider.requests[0].reminder
    assert marked == [0]


@pytest.mark.asyncio
async def test_plan_approval_switches_permission_mode() -> None:
    provider = CapturingProvider()

    async def read_unread():
        return [0], [IncomingMessage(from_="lead", type="plan_approval_response", summary="ok", content="", payload={"approve": True})]

    async def mark_read(indices):
        return None

    tc = TeammateContext("demo", "alice", "agent-1", read_unread=read_unread, mark_read=mark_read)
    session = Session()
    session.append("user", "hi")
    agent = Agent(provider, Registry(), permission_mode=Mode.PLAN, ctx={"teammate": tc})
    _ = [event async for event in agent.run(session, Mode.DEFAULT)]
    assert agent._permission_mode == Mode.DEFAULT
