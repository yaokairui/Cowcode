"""Unified Agent tool for launching SubAgents."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable

import cowcode.run_to_completion  # noqa: F401  # 注册 Agent.run_to_completion
from cowcode.agent import Agent, Event
from cowcode.compact import (
    AutoCompactTrackingState,
    ContentReplacementState,
    RecoveryState,
    new_session_context,
)
from cowcode.fork import build_forked_messages, is_fork_context
from cowcode.runtime import SessionRuntime
from cowcode.session import Session
from cowcode.subagent import Catalog, Definition
from cowcode.task_manager import Manager, PartialState
from cowcode.tool import Registry, Result
from cowcode.tool.filter import FilterParams, apply_agent_tool_filter

AUTO_BACKGROUND_SECONDS = 120.0


@dataclass
class AgentArgs:
    prompt: str
    description: str
    subagent_type: str = ""
    model: str = ""
    run_in_background: bool = False
    name: str = ""


class AgentTool:
    def __init__(
        self,
        catalog: Catalog,
        task_manager: Manager,
        registry: Registry,
        parent_getter: Callable[[], Agent | None],
        messages_getter: Callable[[], list],
        bg_enabled: bool = True,
    ) -> None:
        self._catalog = catalog
        self._task_manager = task_manager
        self._registry = registry
        self._parent_getter = parent_getter
        self._messages_getter = messages_getter
        self._bg_enabled = bg_enabled

    @property
    def read_only(self) -> bool:
        return False

    @property
    def is_system(self) -> bool:
        return True

    def name(self) -> str:
        return "Agent"

    def description(self) -> str:
        names = ", ".join(item.name for item in self._catalog.list())
        return (
            "Launch a SubAgent with an independent context. "
            f"Known subagent_type values: {names}"
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "description": {"type": "string"},
                "subagent_type": {"type": "string"},
                "model": {"type": "string", "enum": ["", "haiku", "sonnet", "opus", "inherit"]},
                "run_in_background": {"type": "boolean"},
                "name": {"type": "string"},
            },
            "required": ["prompt", "description"],
        }

    async def execute(self, args: str) -> Result:
        parsed = _parse_args(args)
        if parsed is None:
            return Result("invalid Agent arguments", is_error=True)
        if not parsed.prompt:
            return Result("prompt is required", is_error=True)
        if not parsed.description:
            return Result("description is required", is_error=True)

        parent = self._parent_getter()
        if parent is None:
            return Result("parent agent is not ready", is_error=True)
        parent_messages = self._messages_getter()
        if is_fork_context(parent_messages):
            return Result("Fork 子 Agent 不能再启动 Agent", is_error=True)

        if parsed.subagent_type:
            definition = self._catalog.resolve(parsed.subagent_type)
            if definition is None:
                return Result(f"未知 subagent_type: {parsed.subagent_type}", is_error=True)
        else:
            definition = self._catalog.fork_definition()

        background = definition.background or parsed.run_in_background or definition.is_fork()
        if background and not self._bg_enabled:
            return Result("后台禁用,无法 Fork", is_error=True)

        allowed = apply_agent_tool_filter(
            FilterParams(
                all=self._registry.names(),
                source=int(definition.source),
                background=background,
                allowed=definition.tools,
                disallowed=definition.disallowed_tools,
                keep_agent=definition.is_fork(),
            )
        )
        sub_agent = _build_subagent(parent, definition, allowed, self._task_manager)
        sub_session = _build_sub_session(definition, parent_messages, parsed.prompt)

        if background:
            task_id = await self._task_manager.launch(
                sub_agent, sub_session, parsed.name, "" if definition.is_fork() else parsed.prompt
            )
            return Result(json.dumps({"task_id": task_id, "status": "async_launched"}))

        events: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=64)
        partial = PartialState()
        aggregator = asyncio.create_task(_aggregate_partial(events, partial))
        handle = asyncio.create_task(sub_agent.run_to_completion(sub_session, parsed.prompt, events))  # type: ignore[attr-defined]
        try:
            final_text = await asyncio.wait_for(
                asyncio.shield(handle), timeout=AUTO_BACKGROUND_SECONDS
            )
            return Result(final_text)
        except asyncio.TimeoutError:
            aggregator.cancel()
            with suppress(asyncio.CancelledError):
                await aggregator
            task_id = await self._task_manager.adopt_running(
                sub_agent, sub_session, parsed.name, events, handle, partial
            )
            return Result(json.dumps({"task_id": task_id, "status": "timed_out_to_background"}))
        except Exception as exc:
            return Result(f"subagent error: {exc}", is_error=True)
        finally:
            if handle.done():
                await _stop_aggregator(events, aggregator)


def _parse_args(args: str) -> AgentArgs | None:
    try:
        data = json.loads(args or "{}")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return AgentArgs(
        prompt=str(data.get("prompt", "") or ""),
        description=str(data.get("description", "") or ""),
        subagent_type=str(data.get("subagent_type", "") or ""),
        model=str(data.get("model", "") or ""),
        run_in_background=bool(data.get("run_in_background", False)),
        name=str(data.get("name", "") or ""),
    )


def _build_subagent(
    parent: Agent, definition: Definition, allowed: list[str], manager: Manager
) -> Agent:
    return Agent(
        parent._provider,
        parent._registry,
        system_prompt=definition.system_prompt or parent._system_prompt,
        environment=parent._environment,
        engine=parent._engine,
        runtime=SessionRuntime(
            replacement=ContentReplacementState(),
            recovery=RecoveryState(),
            auto_tracking=AutoCompactTrackingState(),
            session=new_session_context("."),
        ),
        memory_manager=None,
        allowed_tools=allowed,
        hook_engine=parent._hook_engine,
        max_turns=definition.max_turns,
        permission_mode=definition.permission_mode,
        dont_ask=definition.dont_ask,
        approval_upgrader=manager.upgrade_approval,
        include_system_tools=definition.is_fork(),
    )


def _build_sub_session(definition: Definition, parent_messages: list, prompt: str) -> Session:
    if definition.is_fork():
        return Session.from_messages(build_forked_messages(parent_messages, prompt))
    return Session()


async def _aggregate_partial(events: asyncio.Queue, partial: PartialState) -> None:
    from cowcode.agent import Phase

    while True:
        event = await events.get()
        if event is None:
            return
        if event.tool is not None and event.tool.phase == Phase.START:
            partial.tool_count += 1
            partial.last_activity = event.tool.name
        if event.text:
            partial.last_assistant_text += event.text
        if event.usage is not None:
            partial.usage.input_tokens += event.usage.input_tokens
            partial.usage.output_tokens += event.usage.output_tokens
            partial.usage.cache_write += event.usage.cache_write
            partial.usage.cache_read += event.usage.cache_read


async def _stop_aggregator(events: asyncio.Queue, aggregator: asyncio.Task) -> None:
    with suppress(asyncio.QueueFull):
        events.put_nowait(None)
    if aggregator.done():
        await aggregator
        return
    aggregator.cancel()
    with suppress(asyncio.CancelledError):
        await aggregator
