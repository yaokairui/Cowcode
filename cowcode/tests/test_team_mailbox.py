from __future__ import annotations

import asyncio
import os
import time

import pytest

from cowcode.team.mailbox import Box, Message


@pytest.mark.asyncio
async def test_mailbox_write_read_mark_read(tmp_path) -> None:
    box = Box(tmp_path)
    await box.write(
        "agent-1",
        Message(from_="lead", to="agent-1", summary="hi there", content="hello"),
    )

    messages = await box.read("agent-1")
    assert len(messages) == 1
    assert messages[0].from_ == "lead"
    assert messages[0].content == "hello"

    indices, unread = await box.read_unread("agent-1")
    assert indices == [0]
    assert len(unread) == 1
    await box.mark_read("agent-1", indices)
    assert (await box.read_unread("agent-1"))[1] == []


@pytest.mark.asyncio
async def test_mailbox_concurrent_writes_and_stale_lock(tmp_path) -> None:
    box = Box(tmp_path)
    await asyncio.gather(
        *[
            box.write("agent-1", Message(from_=f"m{i}", to="agent-1", content=str(i)))
            for i in range(10)
        ]
    )
    assert len(await box.read("agent-1")) == 10

    lock = tmp_path / "agent-2.lock"
    lock.write_text("old", encoding="utf-8")
    old = time.time() - 11
    os.utime(lock, (old, old))
    await box.write("agent-2", Message(from_="lead", to="agent-2", content="ok"))
    assert len(await box.read("agent-2")) == 1
