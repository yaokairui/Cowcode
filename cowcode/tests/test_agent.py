from __future__ import annotations

import json
from typing import AsyncIterator

import pytest

from cowcode.agent import Agent, Phase
from cowcode.session import Session, StreamEvent, ToolCall, ToolDefinition
from cowcode.tool import Registry, Result


class FakeTool:
    def __init__(self) -> None:
        self.calls = 0

    def name(self) -> str:
        return "fake_tool"

    def description(self) -> str:
        return "Fake tool."

    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, args: str) -> Result:
        self.calls += 1
        return Result(f"tool result: {args}")


class FakeProvider:
    def __init__(self, second_call_requests_tool: bool = False) -> None:
        self.calls = 0
        self.second_call_requests_tool = second_call_requests_tool

    async def stream(
        self, session: Session, tools: list[ToolDefinition] | None = None
    ) -> AsyncIterator[StreamEvent]:
        self.calls += 1
        if self.calls == 1:
            yield StreamEvent(text="I will inspect it.")
            yield StreamEvent(
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="fake_tool",
                        input=json.dumps({"path": "x"}),
                    )
                ]
            )
            yield StreamEvent(done=True)
            return

        if self.second_call_requests_tool:
            yield StreamEvent(
                tool_calls=[ToolCall(id="call_2", name="fake_tool", input="{}")]
            )
            yield StreamEvent(done=True)
            return

        yield StreamEvent(text="Final answer from tool result.")
        yield StreamEvent(done=True)


@pytest.mark.asyncio
async def test_agent_single_turn_tool_loop() -> None:
    registry = Registry()
    tool = FakeTool()
    registry.register(tool)
    provider = FakeProvider()
    session = Session()
    session.append("user", "use a tool")

    events = [event async for event in Agent(provider, registry).run(session)]

    assert provider.calls == 2
    assert tool.calls == 1
    assert any(event.tool and event.tool.phase == Phase.START for event in events)
    assert any(event.tool and event.tool.phase == Phase.END for event in events)
    assert events[-1].done
    assert session.messages[-3].tool_calls[0].name == "fake_tool"
    assert session.messages[-2].tool_results[0].content.startswith("tool result")
    assert session.messages[-1].content == "Final answer from tool result."


@pytest.mark.asyncio
async def test_agent_ignores_second_round_tool_calls() -> None:
    registry = Registry()
    tool = FakeTool()
    registry.register(tool)
    provider = FakeProvider(second_call_requests_tool=True)
    session = Session()
    session.append("user", "use one tool only")

    events = [event async for event in Agent(provider, registry).run(session)]

    assert provider.calls == 2
    assert tool.calls == 1
    assert events[-1].done
    assert session.messages[-1].role == "assistant"
