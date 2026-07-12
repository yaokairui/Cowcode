"""Agent 长生命周期运行状态。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from cowcode.compact import (
    AutoCompactTrackingState,
    ContentReplacementState,
    RecoveryState,
    SessionContext,
)


@dataclass
class SessionRuntime:
    """跨多轮 run 复用的上下文管理状态。"""

    replacement: ContentReplacementState
    recovery: RecoveryState
    auto_tracking: AutoCompactTrackingState
    session: SessionContext
    context_window: int = 200000
    usage_anchor: int = 0
    anchor_msg_len: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
