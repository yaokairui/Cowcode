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
    turn_count: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def reset_for_new_session(self, session: SessionContext) -> None:
        """切换到新会话，并清空压缩相关运行状态。"""

        self.replacement = ContentReplacementState()
        self.recovery = RecoveryState()
        self.auto_tracking = AutoCompactTrackingState()
        self.session = session
        self.usage_anchor = 0
        self.anchor_msg_len = 0
        self.turn_count = 0
