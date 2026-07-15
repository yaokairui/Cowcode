"""Worktree lifecycle operations."""

from __future__ import annotations

import asyncio
import os
import secrets
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from cowcode.worktree.git import _has_worktree_changes, _run_git
from cowcode.worktree.manager import Manager
from cowcode.worktree.session import WorktreeSession, save_session


class ExitAction(str, Enum):
    KEEP = "keep"
    REMOVE = "remove"


@dataclass
class ExitOptions:
    discard_changes: bool = False


@dataclass
class ExitReport:
    removed: bool
    path: str
    branch: str


@dataclass
class AutoCleanupReport:
    kept: bool
    path: str = ""
    branch: str = ""


class WorktreeHasChangesError(Exception):
    """Worktree has uncommitted changes or local commits."""


async def enter(self: Manager, name: str) -> WorktreeSession:
    async with self.lock:
        wt = self.active.get(name)
        if wt is None:
            raise ValueError(f"未知 worktree: {name}")
        try:
            original_branch = await _run_git(
                self.repo_root, "rev-parse", "--abbrev-ref", "HEAD"
            )
            original_head = await _run_git(self.repo_root, "rev-parse", "HEAD")
        except Exception:
            original_branch = ""
            original_head = ""
        session = WorktreeSession(
            original_cwd=str(Path.cwd()),
            worktree_path=wt.path,
            worktree_name=name,
            original_branch=original_branch,
            original_head_commit=original_head,
            session_id=secrets.token_hex(8),
        )
        self._current_session = session
        save_session(self.session_file, session)
        return session


async def exit(
    self: Manager, name: str, action: ExitAction, opts: ExitOptions
) -> ExitReport:
    async with self.lock:
        session = self._current_session
        if session is None or session.worktree_name != name:
            raise ValueError("只能退出当前 active worktree")
        wt = self.active.get(name)
        if wt is None:
            raise ValueError(f"未知 worktree: {name}")
        if action == ExitAction.REMOVE and not opts.discard_changes:
            if await _has_worktree_changes(wt.path, wt.head_commit):
                raise WorktreeHasChangesError(
                    "worktree has uncommitted changes or new commits"
                )
        with suppress(OSError):
            os.chdir(session.original_cwd)
        self._current_session = None
        save_session(self.session_file, None)
        if action == ExitAction.REMOVE:
            await _remove_locked(self, name, wt.path, wt.branch)
        return ExitReport(
            removed=action == ExitAction.REMOVE, path=wt.path, branch=wt.branch
        )


async def remove(self: Manager, name: str, opts: ExitOptions) -> ExitReport:
    async with self.lock:
        wt = self.active.get(name)
        if wt is None:
            raise ValueError(f"未知 worktree: {name}")
        if not opts.discard_changes and await _has_worktree_changes(
            wt.path, wt.head_commit
        ):
            raise WorktreeHasChangesError(
                "worktree has uncommitted changes or new commits"
            )
        if (
            self._current_session is not None
            and self._current_session.worktree_name == name
        ):
            with suppress(OSError):
                os.chdir(self._current_session.original_cwd)
            self._current_session = None
            save_session(self.session_file, None)
        await _remove_locked(self, name, wt.path, wt.branch)
        return ExitReport(removed=True, path=wt.path, branch=wt.branch)


async def auto_cleanup(self: Manager, name: str) -> AutoCleanupReport:
    async with self.lock:
        wt = self.active.get(name)
    if wt is None:
        return AutoCleanupReport(kept=False)
    if wt.manual:
        return AutoCleanupReport(kept=True, path=wt.path, branch=wt.branch)
    if await _has_worktree_changes(wt.path, wt.head_commit):
        return AutoCleanupReport(kept=True, path=wt.path, branch=wt.branch)
    await remove(self, name, ExitOptions(discard_changes=True))
    return AutoCleanupReport(kept=False)


async def _remove_locked(self: Manager, name: str, path: str, branch: str) -> None:
    await _run_git(self.repo_root, "worktree", "remove", "--force", path)
    await asyncio.sleep(0.1)
    with suppress(Exception):
        await _run_git(self.repo_root, "branch", "-D", branch)
    self.active.pop(name, None)


Manager.enter = enter  # type: ignore[attr-defined]
Manager.exit = exit  # type: ignore[attr-defined]
Manager.remove = remove  # type: ignore[attr-defined]
Manager.auto_cleanup = auto_cleanup  # type: ignore[attr-defined]
