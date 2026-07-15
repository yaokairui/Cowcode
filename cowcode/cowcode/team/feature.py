"""Team 功能开关。"""

from __future__ import annotations


def fork_teammate_enabled(cfg) -> bool:
    return bool(getattr(getattr(cfg, "features", None), "fork_teammate", False))
