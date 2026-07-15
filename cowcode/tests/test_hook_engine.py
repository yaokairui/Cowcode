"""Hook Engine 测试。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from cowcode.hook.engine import Engine
from cowcode.hook.event import Event
from cowcode.hook.executor import ExecutionResult
from cowcode.hook.rule import ActionType, PromptAction, Rule, ShellAction


@dataclass
class FakeExecutor:
    outcomes: list[ExecutionResult]
    calls: list[str]
    started: asyncio.Event | None = None

    async def run(self, rule: Rule, payload, *, blocking: bool) -> ExecutionResult:
        self.calls.append(rule.name)
        if self.started is not None:
            self.started.set()
        if self.outcomes:
            return self.outcomes.pop(0)
        return ExecutionResult()


def _rule(
    name: str,
    event: Event = Event.STOP,
    *,
    only_once: bool = False,
    asyncio_mode: bool = False,
) -> Rule:
    return Rule(
        name=name,
        event=event,
        condition=None,
        action_type=ActionType.PROMPT,
        action=PromptAction(name),
        only_once=only_once,
        asyncio_mode=asyncio_mode,
    )


@pytest.mark.asyncio
async def test_rules_run_in_declared_order() -> None:
    engine = Engine([_rule("first"), _rule("second")], ["hooks.yaml"])
    fake = FakeExecutor([ExecutionResult(), ExecutionResult()], [])
    engine._executor = fake

    await engine.dispatch(Event.STOP, {"event": "Stop"})

    assert fake.calls == ["first", "second"]


@pytest.mark.asyncio
async def test_blocking_event_stops_after_first_block() -> None:
    engine = Engine(
        [_rule("block", Event.PRE_TOOL_USE), _rule("later", Event.PRE_TOOL_USE)], []
    )
    fake = FakeExecutor([ExecutionResult(blocked=True, reason="no")], [])
    engine._executor = fake

    result = await engine.dispatch(Event.PRE_TOOL_USE, {"event": "PreToolUse"})

    assert result.blocked is True
    assert result.reason == "no"
    assert result.blocking_hook_name == "block"
    assert fake.calls == ["block"]


@pytest.mark.asyncio
async def test_non_blocking_event_ignores_blocked_outcome() -> None:
    engine = Engine([_rule("stop", Event.STOP)], [])
    fake = FakeExecutor([ExecutionResult(blocked=True, reason="ignored")], [])
    engine._executor = fake

    result = await engine.dispatch(Event.STOP, {"event": "Stop"})

    assert result.blocked is False
    assert fake.calls == ["stop"]


@pytest.mark.asyncio
async def test_prompt_results_are_accumulated() -> None:
    engine = Engine([_rule("one"), _rule("two")], [])
    fake = FakeExecutor([ExecutionResult(prompt="A"), ExecutionResult(prompt="B")], [])
    engine._executor = fake

    result = await engine.dispatch(Event.STOP, {"event": "Stop"})

    assert result.injected_prompts == ["A", "B"]


@pytest.mark.asyncio
async def test_only_once_skips_until_reset() -> None:
    engine = Engine([_rule("once", only_once=True)], [])
    fake = FakeExecutor([ExecutionResult(), ExecutionResult()], [])
    engine._executor = fake

    await engine.dispatch(Event.STOP, {"event": "Stop"})
    await engine.dispatch(Event.STOP, {"event": "Stop"})
    assert fake.calls == ["once"]

    await engine.reset_for_new_session()
    await engine.dispatch(Event.STOP, {"event": "Stop"})
    assert fake.calls == ["once", "once"]


@pytest.mark.asyncio
async def test_async_rule_starts_background_task_without_blocking() -> None:
    started = asyncio.Event()
    engine = Engine([_rule("async", asyncio_mode=True)], [])
    fake = FakeExecutor([ExecutionResult(blocked=True, reason="ignored")], [], started)
    engine._executor = fake

    result = await engine.dispatch(Event.STOP, {"event": "Stop"})
    await asyncio.wait_for(started.wait(), timeout=1)

    assert result.blocked is False
    assert fake.calls == ["async"]
