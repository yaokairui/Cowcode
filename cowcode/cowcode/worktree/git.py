"""Git helpers for worktree management."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path


async def _run_git(work_dir: str | Path, *args: str) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(work_dir),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    stdout = stdout_b.decode("utf-8", errors="replace").rstrip("\n")
    stderr = stderr_b.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(stderr or f"git {' '.join(args)} failed")
    return stdout


async def _has_worktree_changes(wt_path: str | Path, base_commit: str) -> bool:
    try:
        status = await _run_git(wt_path, "status", "--porcelain")
        if status.strip():
            return True
        count = await _run_git(wt_path, "rev-list", "--count", f"{base_commit}..HEAD")
        return int(count.strip() or "0") > 0
    except Exception:
        return True


def _resolve_head_sha_from_fs(wt_path: str | Path) -> str | None:
    try:
        wt = Path(wt_path)
        git_file = wt / ".git"
        raw_git = git_file.read_text(encoding="utf-8").strip()
        if raw_git.startswith("gitdir:"):
            gitdir_text = raw_git.split(":", 1)[1].strip()
            gitdir = Path(gitdir_text)
            if not gitdir.is_absolute():
                gitdir = (wt / gitdir).resolve()
        else:
            gitdir = git_file
        head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            return (gitdir / ref).read_text(encoding="utf-8").strip()
        return head or None
    except OSError:
        return None
