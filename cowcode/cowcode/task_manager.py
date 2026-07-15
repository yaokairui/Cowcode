"""Background SubAgent task manager."""

from __future__ import annotations

import asyncio
import secrets
import sys
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Awaitable, Callable

import cowcode.run_to_completion  # noqa: F401  # 注册 Agent.run_to_completion
from cowcode.agent import Agent, Event, Phase
from cowcode.session import Session, Usage


class Status(IntEnum):
    RUNNING = 0
    COMPLETED = 1
    FAILED = 2
    CANCELLED = 3

    def __str__(self) -> str:
        return {
            Status.RUNNING: "running",
            Status.COMPLETED: "completed",
            Status.FAILED: "failed",
            Status.CANCELLED: "cancelled",
        }[self]


@dataclass
class PartialState:
    last_assistant_text: str = ""
    tool_count: int = 0
    last_activity: str = ""
    usage: Usage = field(default_factory=Usage)


@dataclass
class BackgroundTask:
    id: str
    name: str
    sub_agent: Agent
    session: Session
    task: str
    status: Status = Status.RUNNING
    result: str = ""
    err: BaseException | None = None
    start_time: float = field(default_factory=time.monotonic)
    end_time: float = 0.0
    handle: asyncio.Task[None] | None = None
    usage: Usage = field(default_factory=Usage)
    tool_count: int = 0
    last_activity: str = ""


class TaskNotFound(Exception):
    pass


class TaskBusy(Exception):
    pass


class Manager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tasks: dict[str, BackgroundTask] = {}
        self._by_name: dict[str, str] = {}
        self._done: asyncio.Queue[str] = asyncio.Queue(maxsize=32)
        self._name_reg = None
        self._done_callbacks: list[Callable[[str], Awaitable[None]]] = []

    async def launch(
        self,
        agent: Agent,
        session: Session,
        name: str,
        task_text: str,
        task_id: str = "",
    ) -> str:
        task_id = task_id or self._next_id()
        bt = BackgroundTask(
            id=task_id, name=name, sub_agent=agent, session=session, task=task_text
        )
        async with self._lock:
            self._tasks[task_id] = bt
            if name:
                self._by_name[name] = task_id
                if self._name_reg is not None:
                    self._name_reg.register(name, task_id)
        self._start_runner(bt, task_text)
        return task_id

    async def adopt_running(
        self,
        agent: Agent,
        session: Session,
        name: str,
        events: asyncio.Queue,
        handle: asyncio.Task,
        partial: PartialState,
    ) -> str:
        task_id = self._next_id()
        bt = BackgroundTask(
            id=task_id,
            name=name,
            sub_agent=agent,
            session=session,
            task="",
            tool_count=partial.tool_count,
            last_activity=partial.last_activity,
            usage=partial.usage,
        )
        bt.handle = handle
        async with self._lock:
            self._tasks[task_id] = bt
            if name:
                self._by_name[name] = task_id
                if self._name_reg is not None:
                    self._name_reg.register(name, task_id)
        asyncio.create_task(self._watch_existing(bt, events, handle))
        return task_id

    def get(self, task_id: str) -> BackgroundTask | None:
        return self._tasks.get(task_id)

    def list(self) -> list[BackgroundTask]:
        return sorted(self._tasks.values(), key=lambda item: item.start_time)

    def subscribe_done(self) -> asyncio.Queue[str]:
        return self._done

    async def stop(self, task_id: str) -> bool:
        task = self.get(task_id)
        if task is None or task.handle is None:
            return False
        task.handle.cancel()
        return True

    async def send_message(self, name: str, message: str) -> str:
        task_id = self._name_reg.resolve(name) if self._name_reg is not None else None
        task_id = task_id or self._by_name.get(name)
        if not task_id:
            raise TaskNotFound(name)
        task = self.get(task_id)
        if task is None:
            raise TaskNotFound(name)
        if task.status == Status.RUNNING:
            raise TaskBusy(name)
        task.session.append("user", message)
        task.status = Status.RUNNING
        task.result = ""
        task.err = None
        task.end_time = 0.0
        self._start_runner(task, "")
        return task.id

    def set_name_registry(self, reg) -> None:
        self._name_reg = reg

    def on_task_done(self, fn: Callable[[str], Awaitable[None]]) -> None:
        self._done_callbacks.append(fn)

    async def upgrade_approval(self, _req) -> tuple[object, bool]:
        return (None, False)

    def _start_runner(self, bt: BackgroundTask, task_text: str) -> None:
        events: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=64)
        aggregator = asyncio.create_task(self._aggregate_events(events, bt))

        async def runner() -> None:
            try:
                text = await bt.sub_agent.run_to_completion(
                    bt.session, task_text, events
                )  # type: ignore[attr-defined]
                bt.result = text
                bt.status = Status.COMPLETED
            except asyncio.CancelledError:
                bt.status = Status.CANCELLED
                bt.result = "cancelled"
            except BaseException as exc:
                bt.status = Status.FAILED
                bt.err = exc
                bt.result = str(exc)
            finally:
                bt.end_time = time.monotonic()
                try:
                    events.put_nowait(None)
                except asyncio.QueueFull:
                    pass
                await aggregator
                self._notify_done(bt.id)
                await self._run_done_callbacks(bt.id)

        bt.handle = asyncio.create_task(runner())

    async def _watch_existing(
        self, bt: BackgroundTask, events: asyncio.Queue, handle: asyncio.Task
    ) -> None:
        aggregator = asyncio.create_task(self._aggregate_events(events, bt))
        try:
            result = await handle
            bt.result = str(result or bt.result)
            bt.status = Status.COMPLETED
        except asyncio.CancelledError:
            bt.status = Status.CANCELLED
            bt.result = "cancelled"
        except BaseException as exc:
            bt.status = Status.FAILED
            bt.err = exc
            bt.result = str(exc)
        finally:
            bt.end_time = time.monotonic()
            aggregator.cancel()
            self._notify_done(bt.id)
            await self._run_done_callbacks(bt.id)

    async def _aggregate_events(
        self, events: asyncio.Queue, bt: BackgroundTask
    ) -> None:
        while True:
            event = await events.get()
            if event is None:
                return
            if event.tool is not None and event.tool.phase == Phase.START:
                bt.tool_count += 1
                bt.last_activity = event.tool.name
            if event.usage is not None:
                bt.usage.input_tokens += event.usage.input_tokens
                bt.usage.output_tokens += event.usage.output_tokens
                bt.usage.cache_write += event.usage.cache_write
                bt.usage.cache_read += event.usage.cache_read

    async def _run_done_callbacks(self, task_id: str) -> None:
        for callback in list(self._done_callbacks):
            try:
                await callback(task_id)
            except Exception as exc:
                print(
                    f"task manager: done callback failed for {task_id}: {exc}",
                    file=sys.stderr,
                )

    def _notify_done(self, task_id: str) -> None:
        try:
            self._done.put_nowait(task_id)
        except asyncio.QueueFull:
            print(
                f"task manager: done queue full, dropping notification for {task_id}",
                file=sys.stderr,
            )

    @staticmethod
    def _next_id() -> str:
        return "task_" + secrets.token_hex(3)
