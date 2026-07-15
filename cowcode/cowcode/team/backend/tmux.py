"""tmux Team 后端。"""

from __future__ import annotations

import asyncio
import os
import sys

from cowcode.team.backend import SpawnRequest
from cowcode.team.types import BackendType


class TmuxBackend:
    def type(self) -> BackendType:
        return BackendType.TMUX

    def build_member_cmd(self, req: SpawnRequest) -> list[str]:
        cmd = [
            sys.executable,
            "-m",
            "cowcode",
            "--team-member",
            "--team",
            req.team_name,
            "--member",
            req.member_name,
            "--agent-id",
            req.agent_id,
            "--session-dir",
            req.session_dir,
            "--worktree",
            req.worktree_path,
        ]
        if req.agent_type:
            cmd.extend(["--agent-type", req.agent_type])
        if req.model:
            cmd.extend(["--model", req.model])
        if req.plan_mode_required:
            cmd.append("--plan-mode")
        return cmd

    async def spawn(self, req: SpawnRequest) -> tuple[str, str]:
        cmd = self.build_member_cmd(req)
        if os.environ.get("TMUX"):
            args = ["tmux", "split-window", "-h", "-P", "-F", "#{pane_id}", "--", *cmd]
        else:
            session_name = f"cowcode-team-{req.team_name}"
            args = ["tmux", "new-session", "-d", "-s", session_name, *cmd]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode(errors="replace") or "tmux spawn failed")
        pane_id = stdout.decode().strip()
        return pane_id, req.agent_id

    async def wake(self, pane_id: str, agent_id: str) -> None:
        if not pane_id:
            return
        proc = await asyncio.create_subprocess_exec("tmux", "send-keys", "-t", pane_id, "", "Enter")
        await proc.wait()

    async def kill(self, pane_id: str, agent_id: str) -> None:
        if not pane_id:
            return
        proc = await asyncio.create_subprocess_exec(
            "tmux", "kill-pane", "-t", pane_id, stderr=asyncio.subprocess.DEVNULL
        )
        await proc.wait()
