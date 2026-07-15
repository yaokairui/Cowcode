"""Sweep stale temporary worktrees."""

from __future__ import annotations

import re
import secrets
from datetime import datetime
from pathlib import Path

from cowcode.worktree.git import _run_git
from cowcode.worktree.lifecycle import ExitOptions, remove
from cowcode.worktree.manager import Manager

EPHEMERAL_PATTERN = re.compile(r"^agent-a[0-9a-f]{7}$")


def random_agent_name() -> str:
    return "agent-a" + secrets.token_hex(4)[:7]


async def sweep_stale(self: Manager, cutoff: datetime) -> list[str]:
    removed: list[str] = []
    current = self._current_session.worktree_path if self._current_session is not None else ""
    for path in Path(self.worktree_dir).iterdir():
        if not path.is_dir() or EPHEMERAL_PATTERN.fullmatch(path.name) is None:
            continue
        if datetime.fromtimestamp(path.stat().st_mtime) > cutoff:
            continue
        if current and str(path.resolve()) == str(Path(current).resolve()):
            continue
        try:
            status = await _run_git(path, "status", "--porcelain")
            if status.strip():
                continue
            unpushed = await _run_git(path, "rev-list", "--max-count=1", "HEAD", "--not", "--remotes")
            if unpushed.strip():
                continue
        except Exception:
            continue
        name = path.name.replace("+", "/")
        if name not in self.active:
            from cowcode.worktree.git import _resolve_head_sha_from_fs
            from cowcode.worktree.manager import Worktree

            head = _resolve_head_sha_from_fs(path)
            if not head:
                continue
            self.active[name] = Worktree(
                name=name,
                path=str(path.resolve()),
                branch=f"worktree-{path.name}",
                based_on=head,
                head_commit=head,
                created=datetime.fromtimestamp(path.stat().st_mtime),
                manual=False,
            )
        try:
            await remove(self, name, ExitOptions(discard_changes=True))
        except Exception:
            continue
        removed.append(name)
    return removed


Manager.sweep_stale = sweep_stale  # type: ignore[attr-defined]
