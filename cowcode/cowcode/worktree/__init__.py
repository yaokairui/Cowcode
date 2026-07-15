"""Git worktree lifecycle support."""

from __future__ import annotations

from cowcode.worktree.slug import flat_slug, validate_slug
from cowcode.worktree.session import WorktreeSession, clear_session, load_session, save_session
from cowcode.worktree.manager import Manager, Worktree

# Import modules for Manager method registration.
from cowcode.worktree import create as _create  # noqa: F401
from cowcode.worktree import lifecycle as _lifecycle  # noqa: F401
from cowcode.worktree import sweep as _sweep  # noqa: F401
from cowcode.worktree.lifecycle import (
    AutoCleanupReport,
    ExitAction,
    ExitOptions,
    ExitReport,
    WorktreeHasChangesError,
)
from cowcode.worktree.sweep import random_agent_name

__all__ = [
    "AutoCleanupReport",
    "ExitAction",
    "ExitOptions",
    "ExitReport",
    "Manager",
    "Worktree",
    "WorktreeHasChangesError",
    "WorktreeSession",
    "clear_session",
    "flat_slug",
    "load_session",
    "random_agent_name",
    "save_session",
    "validate_slug",
]
