"""Adapt worktree.Manager to command UI protocol."""

from __future__ import annotations

from collections.abc import Callable

from cowcode.command.ui import WorktreeSummary
from cowcode.worktree import ExitAction, ExitOptions, Manager


class WorktreeAdapter:
    def __init__(self, manager: Manager, set_active_cwd: Callable[[str], None]) -> None:
        self._manager = manager
        self._set_active_cwd = set_active_cwd

    async def create(self, name: str) -> tuple[str, str]:
        wt = await self._manager.create(name, "HEAD", manual=True)  # type: ignore[attr-defined]
        return wt.path, wt.branch

    def list(self) -> list[WorktreeSummary]:
        current = self._manager.current_session()
        active_name = current.worktree_name if current is not None else ""
        return [
            WorktreeSummary(
                name=wt.name,
                path=wt.path,
                branch=wt.branch,
                active=wt.name == active_name,
                manual=wt.manual,
            )
            for wt in self._manager.list()
        ]

    async def enter(self, name: str) -> None:
        session = await self._manager.enter(name)  # type: ignore[attr-defined]
        self._set_active_cwd(session.worktree_path)

    async def exit(self, action: str, discard: bool) -> bool:
        session = self._manager.current_session()
        if session is None:
            raise ValueError("当前没有 active worktree")
        exit_action = ExitAction.REMOVE if action == "remove" else ExitAction.KEEP
        report = await self._manager.exit(  # type: ignore[attr-defined]
            session.worktree_name,
            exit_action,
            ExitOptions(discard_changes=discard),
        )
        self._set_active_cwd("")
        return report.removed

    async def remove(self, name: str, discard: bool) -> None:
        await self._manager.remove(name, ExitOptions(discard_changes=discard))  # type: ignore[attr-defined]
