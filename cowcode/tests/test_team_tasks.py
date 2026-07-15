from __future__ import annotations

import re

import pytest

from cowcode.team.tasks import Filter, Patch, Status, Store, Task


@pytest.mark.asyncio
async def test_tasks_create_update_bidirectional_and_ready(tmp_path) -> None:
    store = Store(tmp_path / "tasks.json")
    blocker = await store.create(Task(title="blocker"))
    task = await store.create(Task(title="task"))
    assert re.fullmatch(r"task_[0-9a-f]{6}", task)

    await store.update(task, Patch(add_blocked_by=[blocker]))
    loaded = await store.get(task)
    other = await store.get(blocker)
    assert loaded.blocked_by == [blocker]
    assert task in other.blocks

    pending = await store.list_(Filter(Status.PENDING))
    by_id = {item.id: item for item in pending}
    assert by_id[task].is_ready is False

    await store.update(blocker, Patch(status=Status.COMPLETED))
    ready = {item.id: item for item in await store.list_(Filter(Status.PENDING))}
    assert ready[task].is_ready is True
