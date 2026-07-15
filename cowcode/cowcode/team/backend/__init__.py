"""Team 后端协议与工厂。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cowcode.team.types import BackendType


class Backend(Protocol):
    def type(self) -> BackendType: ...

    async def spawn(self, req: "SpawnRequest") -> tuple[str, str]: ...

    async def wake(self, pane_id: str, agent_id: str) -> None: ...

    async def kill(self, pane_id: str, agent_id: str) -> None: ...


@dataclass
class SpawnRequest:
    team_name: str
    member_name: str
    agent_id: str
    worktree_path: str
    session_dir: str
    agent_type: str
    model: str
    initial_prompt: str
    plan_mode_required: bool = False
    sub_agent: Any = None
    conv: Any = None
    task_mgr: Any = None


def new_backend(t: BackendType, **deps: Any) -> Backend:
    if t == BackendType.TMUX:
        from cowcode.team.backend.tmux import TmuxBackend

        return TmuxBackend()
    if t == BackendType.ITERM2:
        from cowcode.team.backend.iterm2 import Iterm2Backend

        return Iterm2Backend()
    from cowcode.team.backend.inprocess import InProcessBackend

    return InProcessBackend(deps.get("task_mgr"))
