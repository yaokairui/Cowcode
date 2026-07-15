"""SessionRuntime 测试。"""

from __future__ import annotations

import pytest

from cowcode.compact import (
    AutoCompactTrackingState,
    ContentReplacementState,
    RecoveryState,
    SessionContext,
)
from cowcode.runtime import SessionRuntime


@pytest.mark.asyncio
async def test_reset_for_new_session_resets_compact_state() -> None:
    old_session = SessionContext("old", "/old", "/old/tool-results")
    runtime = SessionRuntime(
        replacement=ContentReplacementState(),
        recovery=RecoveryState(),
        auto_tracking=AutoCompactTrackingState(),
        session=old_session,
        usage_anchor=10,
        anchor_msg_len=2,
        turn_count=3,
    )
    old_replacement = runtime.replacement
    old_recovery = runtime.recovery
    old_tracking = runtime.auto_tracking
    new_session = SessionContext("new", "/new", "/new/tool-results")

    await runtime.reset_for_new_session(new_session)

    assert runtime.session is new_session
    assert runtime.usage_anchor == 0
    assert runtime.anchor_msg_len == 0
    assert runtime.turn_count == 0
    assert runtime.replacement is not old_replacement
    assert runtime.recovery is not old_recovery


@pytest.mark.asyncio
async def test_pending_reminders_take_and_clear() -> None:
    runtime = SessionRuntime(
        replacement=ContentReplacementState(),
        recovery=RecoveryState(),
        auto_tracking=AutoCompactTrackingState(),
        session=SessionContext("s", "/cwd", "/tmp"),
    )

    await runtime.append_reminders(["one", "two"])

    assert await runtime.take_reminders() == ["one", "two"]
    assert await runtime.take_reminders() == []


@pytest.mark.asyncio
async def test_reset_for_new_session_clears_reminders() -> None:
    runtime = SessionRuntime(
        replacement=ContentReplacementState(),
        recovery=RecoveryState(),
        auto_tracking=AutoCompactTrackingState(),
        session=SessionContext("s", "/cwd", "/tmp"),
    )
    await runtime.append_reminders(["one"])

    await runtime.reset_for_new_session(SessionContext("new", "/cwd", "/tmp"))

    assert await runtime.take_reminders() == []
