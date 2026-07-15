"""Worktree manager core."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cowcode.worktree.git import _resolve_head_sha_from_fs
from cowcode.worktree.session import WorktreeSession, clear_session, load_session
from cowcode.worktree.slug import flat_slug

DEFAULT_SYMLINK_DIRS = ["node_modules", ".venv", "vendor"]


@dataclass
class Worktree:
    name: str
    path: str
    branch: str
    based_on: str
    head_commit: str
    created: datetime
    manual: bool


class Manager:
    """Manage git worktrees owned by one repository."""

    def __init__(self, repo_root: str) -> None:
        root = Path(repo_root).resolve()
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise ValueError("not a git repo root")
        git_root = Path(proc.stdout.strip()).resolve()
        if git_root != root:
            raise ValueError("not a git repo root")

        self.repo_root = str(root)
        self.worktree_dir = root / ".cowcode" / "worktrees"
        self.session_file = root / ".cowcode" / "worktree_session.json"
        self.symlink_dirs = list(DEFAULT_SYMLINK_DIRS)
        self.lock = asyncio.Lock()
        self.active: dict[str, Worktree] = {}
        self._current_session: WorktreeSession | None = None

        self.worktree_dir.mkdir(parents=True, exist_ok=True)
        self._load_current_session()
        self._scan_existing_worktrees()

    def list(self) -> list[Worktree]:
        return [self.active[name] for name in sorted(self.active)]

    def get(self, name: str) -> Worktree | None:
        return self.active.get(name)

    def current_session(self) -> WorktreeSession | None:
        return self._current_session

    def _load_current_session(self) -> None:
        try:
            session = load_session(self.session_file)
        except Exception as exc:
            print(f"worktree: session 文件损坏,已清空: {exc}", file=sys.stderr)
            clear_session(self.session_file)
            self._current_session = None
            return
        if session is not None and not Path(session.worktree_path).exists():
            print("worktree: session worktree gone, cleared", file=sys.stderr)
            clear_session(self.session_file)
            session = None
        self._current_session = session

    def _scan_existing_worktrees(self) -> None:
        for path in self.worktree_dir.iterdir():
            if not path.is_dir():
                continue
            head = _resolve_head_sha_from_fs(path)
            if not head:
                continue
            name = path.name.replace("+", "/")
            flat = flat_slug(name)
            self.active[name] = Worktree(
                name=name,
                path=str(path.resolve()),
                branch=f"worktree-{flat}",
                based_on=head,
                head_commit=head,
                created=datetime.fromtimestamp(path.stat().st_mtime),
                manual=True,
            )
