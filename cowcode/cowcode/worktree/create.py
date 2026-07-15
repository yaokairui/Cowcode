"""Worktree creation and post-creation setup."""

from __future__ import annotations

import fnmatch
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from cowcode.worktree.git import _resolve_head_sha_from_fs, _run_git
from cowcode.worktree.manager import Manager, Worktree
from cowcode.worktree.slug import flat_slug, validate_slug


async def create(
    self: Manager, name: str, base_ref: str = "HEAD", manual: bool = False
) -> Worktree:
    validate_slug(name)
    async with self.lock:
        if name in self.active:
            raise ValueError(f"worktree already active: {name}")
        flat = flat_slug(name)
        wt_path = self.worktree_dir / flat
        branch = f"worktree-{flat}"
        if wt_path.exists():
            head = _resolve_head_sha_from_fs(wt_path)
            if not head:
                raise RuntimeError(f"cannot resolve worktree HEAD: {wt_path}")
            wt = Worktree(
                name=name,
                path=str(wt_path.resolve()),
                branch=branch,
                based_on=head,
                head_commit=head,
                created=datetime.fromtimestamp(wt_path.stat().st_mtime),
                manual=manual,
            )
            self.active[name] = wt
            return wt

        try:
            await _run_git(
                self.repo_root, "worktree", "add", "-B", branch, str(wt_path), base_ref
            )
        except Exception:
            shutil.rmtree(wt_path, ignore_errors=True)
            raise

        await _perform_post_creation_setup(
            Path(self.repo_root), wt_path, self.symlink_dirs
        )
        head = await _run_git(wt_path, "rev-parse", "HEAD")
        wt = Worktree(
            name=name,
            path=str(wt_path.resolve()),
            branch=branch,
            based_on=base_ref,
            head_commit=head,
            created=datetime.now(),
            manual=manual,
        )
        self.active[name] = wt
        return wt


async def _perform_post_creation_setup(
    repo_root: Path, wt_path: Path, symlink_dirs: list[str]
) -> None:
    steps = [
        ("configs", lambda: _copy_local_configs(repo_root, wt_path)),
        ("hooks", lambda: _setup_git_hooks(repo_root, wt_path)),
        ("symlinks", lambda: _symlink_large_dirs(repo_root, wt_path, symlink_dirs)),
        ("include", lambda: _copy_included_ignored(repo_root, wt_path)),
    ]
    for name, fn in steps:
        try:
            result = fn()
            if hasattr(result, "__await__"):
                await result
        except Exception as exc:
            print(f"worktree: setup {name}: {exc}", file=sys.stderr)


def _copy_local_configs(repo_root: Path, wt_path: Path) -> None:
    for rel in (".cowcode/config.yaml", ".cowcode/settings.local.yaml"):
        src = repo_root / rel
        dst = wt_path / rel
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


async def _setup_git_hooks(repo_root: Path, wt_path: Path) -> None:
    hooks_path = ""
    husky = repo_root / ".husky"
    if husky.is_dir():
        hooks_path = str(husky.resolve())
    else:
        try:
            hooks_path = await _run_git(repo_root, "config", "--get", "core.hooksPath")
        except Exception:
            hooks_path = ""
        if hooks_path and not Path(hooks_path).is_absolute():
            hooks_path = str((repo_root / hooks_path).resolve())
    if hooks_path:
        await _run_git(wt_path, "config", "core.hooksPath", hooks_path)


def _symlink_large_dirs(
    repo_root: Path, wt_path: Path, symlink_dirs: list[str]
) -> None:
    for rel in symlink_dirs:
        src = repo_root / rel
        dst = wt_path / rel
        if src.exists() and not dst.exists():
            os.symlink(src, dst, target_is_directory=src.is_dir())


async def _copy_included_ignored(repo_root: Path, wt_path: Path) -> None:
    include = repo_root / ".worktreeinclude"
    if not include.exists():
        return
    patterns = [
        line.strip() for line in include.read_text(encoding="utf-8").splitlines()
    ]
    patterns = [p for p in patterns if p and not p.startswith("#")]
    if not patterns:
        return
    listed = await _run_git(
        repo_root,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
    )
    for rel in listed.splitlines():
        rel = rel.rstrip("/")
        if not rel or not any(
            fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(Path(rel).name, pat)
            for pat in patterns
        ):
            continue
        src = repo_root / rel
        dst = wt_path / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        elif src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)


Manager.create = create  # type: ignore[attr-defined]
