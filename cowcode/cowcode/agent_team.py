"""Agent 与 Team 的解耦接口。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class IncomingMessage:
    from_: str
    type: str
    summary: str
    content: str
    payload: dict[str, Any] | None = None
    timestamp: int = 0


@dataclass
class TeammateContext:
    team_name: str
    member_name: str
    agent_id: str
    backend_type: str = "in-process"
    read_unread: (
        Callable[[], Awaitable[tuple[list[int], list[IncomingMessage]]]] | None
    ) = None
    mark_read: Callable[[list[int]], Awaitable[None]] | None = None


@dataclass
class TeamSpawnRequest:
    team_name: str
    prompt: str
    description: str = ""
    subagent_type: str = ""
    model: str = ""
    member_name: str = ""
    plan_mode_required: bool = False
    parent: Any = None
    parent_messages: list[Any] = field(default_factory=list)
    ctx: dict[str, Any] = field(default_factory=dict)


class TeamHook(Protocol):
    async def spawn_teammate(self, req: TeamSpawnRequest) -> str: ...

    def is_teammate_context(self, ctx: Any) -> tuple[str, str, bool]: ...


WITH_TEAMMATE_KEY = "teammate"


def with_teammate_context(
    ctx: dict[str, Any] | None, tc: TeammateContext
) -> dict[str, Any]:
    out = dict(ctx or {})
    out[WITH_TEAMMATE_KEY] = tc
    return out


def teammate_context_from_ctx(ctx: Any) -> TeammateContext | None:
    if isinstance(ctx, dict):
        value = ctx.get(WITH_TEAMMATE_KEY)
        return value if isinstance(value, TeammateContext) else None
    return None
