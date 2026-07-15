"""同进程 Team 后端。"""

from __future__ import annotations

from cowcode.team.backend import SpawnRequest
from cowcode.team.types import BackendType


class InProcessBackend:
    def __init__(self, task_mgr) -> None:
        self._task_mgr = task_mgr

    def type(self) -> BackendType:
        return BackendType.IN_PROCESS

    async def spawn(self, req: SpawnRequest) -> tuple[str, str]:
        task_mgr = req.task_mgr or self._task_mgr
        if task_mgr is None:
            raise RuntimeError("task manager not configured")
        task_id = await task_mgr.launch(
            req.sub_agent,
            req.conv,
            req.member_name,
            req.initial_prompt,
            task_id=req.agent_id,
        )
        return "", task_id

    async def wake(self, pane_id: str, agent_id: str) -> None:
        return None

    async def kill(self, pane_id: str, agent_id: str) -> None:
        if self._task_mgr is not None:
            await self._task_mgr.stop(agent_id)
