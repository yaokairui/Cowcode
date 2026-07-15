"""Worktree slug validation."""

from __future__ import annotations

import re

_SEGMENT_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


def validate_slug(name: str) -> None:
    """Validate a user-provided worktree slug."""

    if not name:
        raise ValueError("worktree name is required")
    if len(name) > 64:
        raise ValueError("worktree name must be at most 64 characters")
    if name.startswith("/") or name.endswith("/"):
        raise ValueError("worktree name must not start or end with /")
    if "//" in name:
        raise ValueError("worktree name must not contain empty path segments")
    for segment in name.split("/"):
        if segment in {".", ".."}:
            raise ValueError("worktree name must not contain . or .. segments")
        if _SEGMENT_RE.fullmatch(segment) is None:
            raise ValueError(
                "worktree name segments may only contain letters, digits, dot, underscore, and dash"
            )


def flat_slug(name: str) -> str:
    """Return the filesystem-safe slug used for paths and branch names."""

    return name.replace("/", "+")
