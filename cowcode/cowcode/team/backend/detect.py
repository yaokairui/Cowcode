"""Team 后端自动检测。"""

from __future__ import annotations

import os
import shutil

from cowcode.team.types import BackendType


def detect() -> BackendType:
    if os.environ.get("TMUX"):
        return BackendType.TMUX
    if os.environ.get("TERM_PROGRAM") == "iTerm.app" and shutil.which("it2"):
        return BackendType.ITERM2
    if shutil.which("tmux"):
        return BackendType.TMUX
    return BackendType.IN_PROCESS
