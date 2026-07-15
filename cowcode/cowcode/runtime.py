"""Agent 长生命周期运行状态。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from cowcode.compact import (
    AutoCompactTrackingState,
    ContentReplacementState,
    RecoveryState,
    SessionContext,
)
from cowcode.skills.active import ActiveSkills


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
    active_skills: ActiveSkills = field(default_factory=ActiveSkills)
    pending_reminders: list[str] = field(default_factory=list)
    hook_engine: Any | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    reminder_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def reset_for_new_session(self, session: SessionContext) -> None:
        """切换到新会话，并清空压缩、Skill 和 Hook 运行状态。"""

        self.replacement = ContentReplacementState()
        self.recovery = RecoveryState()
        self.auto_tracking = AutoCompactTrackingState()
        self.session = session
        self.usage_anchor = 0
        self.anchor_msg_len = 0
        self.turn_count = 0
        self.active_skills.clear()
        async with self.reminder_lock:
            self.pending_reminders.clear()
        if self.hook_engine is not None:
            await self.hook_engine.reset_for_new_session()

    async def append_reminders(self, prompts: list[str]) -> None:
        """追加下一轮请求要注入的 reminder。"""

        if not prompts:
            return
        async with self.reminder_lock:
            self.pending_reminders.extend(prompts)

    async def take_reminders(self) -> list[str]:
        """取出并清空待注入 reminder。"""

        async with self.reminder_lock:
            prompts = list(self.pending_reminders)
            self.pending_reminders.clear()
        return prompts
