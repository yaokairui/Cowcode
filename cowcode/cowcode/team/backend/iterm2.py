"""iTerm2 Team 后端。"""

from __future__ import annotations

import asyncio
import shlex

from cowcode.team.backend import SpawnRequest
from cowcode.team.backend.tmux import TmuxBackend
from cowcode.team.types import BackendType


class Iterm2Backend:
    def type(self) -> BackendType:
        return BackendType.ITERM2

    def build_member_cmd(self, req: SpawnRequest) -> str:
        return " ".join(
            shlex.quote(part) for part in TmuxBackend().build_member_cmd(req)
        )

    async def spawn(self, req: SpawnRequest) -> tuple[str, str]:
        proc = await asyncio.create_subprocess_exec(
            "it2",
            "split",
            "--new-pane",
            "--command",
            self.build_member_cmd(req),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode(errors="replace") or "iterm2 spawn failed")
        return stdout.decode().strip(), req.agent_id

    async def wake(self, pane_id: str, agent_id: str) -> None:
        if not pane_id:
            return
        proc = await asyncio.create_subprocess_exec(
            "it2", "send-text", "--pane", pane_id, ""
        )
        await proc.wait()

    async def kill(self, pane_id: str, agent_id: str) -> None:
        if not pane_id:
            return
        proc = await asyncio.create_subprocess_exec(
            "it2", "close-pane", "--pane", pane_id
        )
        await proc.wait()
