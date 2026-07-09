"""Single-turn tool orchestration for Cowcode."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator

from cowcode.provider import Provider
from cowcode.session import Session, ToolCall, ToolResult
from cowcode.tool import DEFAULT_TIMEOUT, Registry, truncate_text


class Phase(Enum):
    START = "start"
    END = "end"


@dataclass
class ToolEvent:
    """UI 可渲染的工具执行事件。"""

    name: str
    args: str = ""
    phase: Phase = Phase.START
    result: str = ""
    is_error: bool = False


@dataclass
class Event:
    """Agent 对外事件流。"""

    text: str = ""
    tool: ToolEvent | None = None
    done: bool = False
    err: Exception | None = None


class Agent:
    """执行 ch03 的单轮工具闭环。"""

    def __init__(self, provider: Provider, registry: Registry) -> None:
        self._provider = provider
        self._registry = registry

    async def run(self, session: Session) -> AsyncIterator[Event]:
        definitions = self._registry.definitions()

        preamble = ""
        calls: list[ToolCall] = []
        try:
            async for event in self._provider.stream(session, definitions):
                if event.text:
                    preamble += event.text
                    yield Event(text=event.text)
                if event.tool_calls:
                    calls.extend(event.tool_calls)
        except Exception as exc:
            yield Event(err=exc)
            return

        if not calls:
            if preamble:
                session.append("assistant", preamble)
            yield Event(done=True)
            return

        session.add_assistant_with_tool_calls(preamble, calls)
        results: list[ToolResult] = []
        for call in calls:
            args_preview = truncate_text(call.input or "{}", max_lines=3, max_chars=180)
            yield Event(tool=ToolEvent(name=call.name, args=args_preview))
            result = await self._registry.execute(
                call.name, call.input or "{}", timeout=DEFAULT_TIMEOUT
            )
            results.append(
                ToolResult(
                    tool_call_id=call.id,
                    content=result.content,
                    is_error=result.is_error,
                )
            )
            yield Event(
                tool=ToolEvent(
                    name=call.name,
                    args=args_preview,
                    phase=Phase.END,
                    result=result.content,
                    is_error=result.is_error,
                )
            )

        session.add_tool_results(results)
        final = ""
        try:
            async for event in self._provider.stream(session, definitions):
                if event.text:
                    final += event.text
                    yield Event(text=event.text)
                # ch03 只执行一轮工具；续答阶段的工具调用忽略。
        except Exception as exc:
            yield Event(err=exc)
            return

        if not final:
            final = "Tool results were returned, but the model did not provide a final answer."
            yield Event(text=final)
        session.append("assistant", final)
        yield Event(done=True)
