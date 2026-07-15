"""SubAgent run-to-completion helpers."""

from __future__ import annotations

import asyncio

from cowcode.agent import Agent, Event, MAX_ITERATIONS, NOTICE_MAX_ITER
from cowcode.permission import Mode
from cowcode.session import Session


class MaxTurnsReached(RuntimeError):
    """Raised when a SubAgent reaches its configured max turn limit."""

    def __init__(self, final_text: str) -> None:
        super().__init__("subagent reached max turns")
        self.final_text = final_text


async def run_to_completion(
    self: Agent,
    session: Session,
    task: str,
    events: asyncio.Queue[Event | None] | None = None,
) -> str:
    """Run an Agent until it produces a final assistant message."""

    if task:
        session.append("user", task)
    final_text = ""
    max_turns = getattr(self, "_max_turns", 0) or MAX_ITERATIONS
    turn_count = 0
    async for event in self.run(
        session,
        getattr(self, "_permission_mode", None) or Mode.DEFAULT,
        asyncio.Event(),
    ):
        if events is not None:
            try:
                events.put_nowait(event)
            except asyncio.QueueFull:
                pass
        if event.text:
            final_text += event.text
        if event.err is not None:
            raise event.err
        if event.iter > 0:
            turn_count = max(turn_count, event.iter)
        if event.done:
            break
    if not final_text.strip():
        final_text = next(
            (msg.content for msg in reversed(session.get_history()) if msg.role == "assistant"),
            "",
        )
    if turn_count >= max_turns and final_text.endswith(NOTICE_MAX_ITER):
        raise MaxTurnsReached(final_text)
    return final_text


Agent.run_to_completion = run_to_completion  # type: ignore[attr-defined, method-assign]
