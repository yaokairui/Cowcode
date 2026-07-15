"""Task notification reminder helpers."""

from __future__ import annotations

from cowcode.task_manager import BackgroundTask


def build_task_notification(task: BackgroundTask) -> str:
    name = f' (name="{task.name}")' if task.name else ""
    result = task.result
    if task.err is not None and not result:
        result = str(task.err)
    return (
        "<task-notification>\n"
        f"Task {task.id}{name}: {task.status}\n"
        f"Result: {result}\n"
        "</task-notification>"
    )


async def consume_task_done(app) -> None:
    queue = app.task_manager.subscribe_done()
    while True:
        task_id = await queue.get()
        task = app.task_manager.get(task_id)
        if task is None:
            continue
        await app._runtime.append_reminders([build_task_notification(task)])
