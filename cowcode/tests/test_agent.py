"""ch04 Agent Loop 单测——多轮、分批并发、停止条件、Plan 工具集。"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import pytest

from cowcode.agent import (
    MAX_ITERATIONS,
    MAX_UNKNOWN_RUN,
    NOTICE_MAX_ITER,
    NOTICE_UNKNOWN_TOOLS,
    Agent,
    Mode,
    Phase,
)
from cowcode.prompt import PLAN_MODE_REMINDER
from cowcode.session import Session, StreamEvent, ToolCall, Usage
from cowcode.tool import Registry, Result


class FakeTool:
    """插桩工具：可配 name、read_only、execute 行为。"""

    def __init__(
        self,
        name: str = "fake_tool",
        read_only: bool = False,
        execute_fn=None,
    ) -> None:
        self._name = name
        self._read_only = read_only
        self._execute_fn = execute_fn
        self.calls: list[str] = []

    @property
    def read_only(self) -> bool:
        return self._read_only

    def name(self) -> str:
        return self._name

    def description(self) -> str:
        return f"Fake tool: {self._name}."

    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "required": []}

    async def execute(self, args: str) -> Result:
        self.calls.append(args)
        if self._execute_fn is not None:
            return await self._execute_fn(self, args)
        return Result(f"result from {self._name}")


class FakeProvider:
    """多轮脚本 fake provider——按 scripts 列表逐次返回。"""

    def __init__(
        self,
        scripts: list[list[StreamEvent]],
        record_streams: bool = False,
    ) -> None:
        self.scripts = scripts
        self.call_idx = 0
        self.record_streams = record_streams
        self.captured_defs: list[list] = []
        self.captured_suffixes: list[str] = []

    async def stream(
        self,
        session: Session,
        tools: list | None = None,
        system_suffix: str = "",
    ) -> AsyncIterator[StreamEvent]:
        if self.call_idx >= len(self.scripts):
            # 脚本耗尽：返回纯文本终止
            yield StreamEvent(text="Done.")
            yield StreamEvent(done=True)
            return
        script = self.scripts[self.call_idx]
        if self.record_streams:
            self.captured_defs.append(
                [(t.name if hasattr(t, "name") else str(t)) for t in (tools or [])]
            )
            self.captured_suffixes.append(system_suffix)
        for ev in script:
            yield ev
        self.call_idx += 1


def _text(text: str) -> StreamEvent:
    return StreamEvent(text=text)


def _done() -> StreamEvent:
    return StreamEvent(done=True)


def _usage(inp: int = 100, out: int = 50) -> StreamEvent:
    return StreamEvent(usage=Usage(input_tokens=inp, output_tokens=out))


def _tool_call(
    name: str = "fake_tool", input_str: str = "{}", call_id: str = "c1"
) -> StreamEvent:
    return StreamEvent(tool_calls=[ToolCall(id=call_id, name=name, input=input_str)])


@pytest.mark.asyncio
async def test_text_is_yielded_before_provider_stream_completes() -> None:
    """首段文本必须在 Provider 流结束前到达消费者。"""
    release_stream = asyncio.Event()
    stream_finished = asyncio.Event()

    class GatedProvider:
        async def stream(self, session, tools=None, system_suffix=""):
            try:
                yield StreamEvent(text="Hello")
                await release_stream.wait()
                yield StreamEvent(text=" world")
                yield _usage(12, 5)
                yield _done()
            finally:
                stream_finished.set()

    session = Session()
    session.append("user", "say hello")
    stream = Agent(GatedProvider(), Registry()).run(
        session, Mode.NORMAL, asyncio.Event()
    )

    iteration = await anext(stream)
    first_text = await asyncio.wait_for(anext(stream), timeout=0.5)

    assert iteration.iter == 1
    assert first_text.text == "Hello"
    assert not release_stream.is_set()
    assert not stream_finished.is_set()

    release_stream.set()
    remaining = [event async for event in stream]

    assert any(event.text == " world" for event in remaining)
    assert any(event.usage == Usage(input_tokens=12, output_tokens=5) for event in remaining)
    assert remaining[-1].done
    assert stream_finished.is_set()
    assert session.messages[-1].content == "Hello world"


@pytest.mark.asyncio
async def test_tool_start_is_yielded_before_execution_completes() -> None:
    """工具 START 必须在工具执行完成前到达消费者。"""
    tool_entered = asyncio.Event()
    release_tool = asyncio.Event()
    tool_finished = asyncio.Event()

    async def gated_execute(tool: FakeTool, args: str) -> Result:
        tool_entered.set()
        await release_tool.wait()
        tool_finished.set()
        return Result("finished")

    registry = Registry()
    registry.register(
        FakeTool("read_file", read_only=True, execute_fn=gated_execute)
    )
    provider = FakeProvider(
        scripts=[
            [_tool_call("read_file", call_id="read-1"), _done()],
            [_text("done"), _done()],
        ]
    )
    session = Session()
    session.append("user", "read")
    stream = Agent(provider, registry).run(session, Mode.NORMAL, asyncio.Event())

    assert (await anext(stream)).iter == 1
    start = await asyncio.wait_for(anext(stream), timeout=0.5)
    assert start.tool is not None
    assert start.tool.phase == Phase.START
    assert not tool_finished.is_set()

    pending = asyncio.create_task(anext(stream))
    await asyncio.wait_for(tool_entered.wait(), timeout=0.5)
    await asyncio.sleep(0)
    assert not pending.done()

    release_tool.set()
    end = await asyncio.wait_for(pending, timeout=0.5)
    assert end.tool is not None
    assert end.tool.phase == Phase.END
    assert tool_finished.is_set()

    remaining = [event async for event in stream]
    assert remaining[-1].done


# ============================================================
# 场景 A：多轮链路（AC1）
# ============================================================
@pytest.mark.asyncio
async def test_multi_turn_loop() -> None:
    """一轮工具调用 → 二轮纯文本 → 自然完成。"""
    registry = Registry()
    tool = FakeTool()
    registry.register(tool)

    provider = FakeProvider(
        scripts=[
            [
                _text("Let me read that file."),
                _tool_call("fake_tool", json.dumps({"path": "x"})),
                _usage(),
                _done(),
            ],
            [
                _text("Based on the file, here is the answer."),
                _usage(),
                _done(),
            ],
        ]
    )

    session = Session()
    session.append("user", "read a file and summarize")

    events = [
        ev
        async for ev in Agent(provider, registry).run(
            session, Mode.NORMAL, asyncio.Event()
        )
    ]

    # 断言事件序列
    texts = [ev.text for ev in events if ev.text]
    tools = [ev.tool for ev in events if ev.tool is not None]
    iters = [ev.iter for ev in events if ev.iter > 0]
    done_event = events[-1]

    assert provider.call_idx == 2
    assert len(tool.calls) == 1
    assert any("Let me read" in t for t in texts)
    assert any("Based on the file" in t for t in texts)
    assert len(tools) == 2  # start + end
    assert any(t.name == "fake_tool" and t.phase == Phase.START for t in tools)
    assert any(t.name == "fake_tool" and t.phase == Phase.END for t in tools)
    assert 1 in iters
    assert 2 in iters
    assert done_event.done
    # 历史合法
    assert session.messages[-1].role == "assistant"
    assert "Based on the file" in session.messages[-1].content
    # 中间应包含 tool_use 回合 + tool 回合
    roles = [m.role for m in session.messages]
    assert "tool" in roles


# ============================================================
# 场景 B：迭代上限（AC3）
# ============================================================
@pytest.mark.asyncio
async def test_max_iterations() -> None:
    """Fake 每次都返回工具调用 → 达上限后停。"""
    registry = Registry()
    tool = FakeTool()
    registry.register(tool)

    # 无限循环——实际 provider 在脚本耗尽后返回纯文本
    # 这里用足够长脚本 + 末尾不返回 done 但每次都返回工具调用
    infinite_scripts = [
        [_text("trying..."), _tool_call("fake_tool"), _done()]
        for _ in range(MAX_ITERATIONS + 5)
    ]
    provider = FakeProvider(scripts=infinite_scripts)

    session = Session()
    session.append("user", "keep going")

    events = [
        ev
        async for ev in Agent(provider, registry).run(
            session, Mode.NORMAL, asyncio.Event()
        )
    ]

    done_events = [ev for ev in events if ev.done]
    notices = [ev.notice for ev in events if ev.notice]
    assert len(done_events) == 1
    assert done_events[0].done
    assert any(NOTICE_MAX_ITER in n for n in notices)
    assert session.last_role() == "assistant"
    assert NOTICE_MAX_ITER in session.messages[-1].content
    # 恰好 MAX_ITERATIONS 次请求
    assert provider.call_idx == MAX_ITERATIONS


# ============================================================
# 场景 C：连续未知工具（AC4）
# ============================================================
@pytest.mark.asyncio
async def test_unknown_tools_stop() -> None:
    """连续 MAX_UNKNOWN_RUN 轮全是未注册工具 → 停。"""
    registry = Registry()
    # 不注册任何工具——所有 tool_call 都是 unknown

    scripts = [
        [
            _text("let me try..."),
            _tool_call("nonexistent_tool", "{}"),
            _done(),
        ]
        for _ in range(MAX_UNKNOWN_RUN + 5)
    ]
    provider = FakeProvider(scripts=scripts)

    session = Session()
    session.append("user", "use a tool that doesn't exist")

    events = [
        ev
        async for ev in Agent(provider, registry).run(
            session, Mode.NORMAL, asyncio.Event()
        )
    ]

    notices = [ev.notice for ev in events if ev.notice]
    assert any(NOTICE_UNKNOWN_TOOLS in n for n in notices)
    # 应停在 MAX_UNKNOWN_RUN 轮
    assert provider.call_idx == MAX_UNKNOWN_RUN


@pytest.mark.asyncio
async def test_unknown_tools_reset_on_mixed() -> None:
    """混入已知工具后计数重置。"""
    registry = Registry()
    tool = FakeTool()
    registry.register(tool)

    # 第 1 轮：未知 + 已知混合 → 计数重置
    # 第 2 轮：未知 + 已知混合 → 计数重置
    # ... 不会触发 MAX_UNKNOWN_RUN
    scripts = [
        [
            _text("mixed"),
            _tool_call("nonexistent", "{}"),
            _tool_call("fake_tool", "{}"),
            _done(),
        ]
        for _ in range(MAX_UNKNOWN_RUN + 5)
    ]
    provider = FakeProvider(scripts=scripts)

    session = Session()
    session.append("user", "mixed calls")

    events = [
        ev
        async for ev in Agent(provider, registry).run(
            session, Mode.NORMAL, asyncio.Event()
        )
    ]

    # 没有未知工具停止事件
    notices = [ev.notice for ev in events if ev.notice]
    assert not any(NOTICE_UNKNOWN_TOOLS in n for n in notices)
    # 至少跑了超过 MAX_UNKNOWN_RUN 轮（因为每次混入了已知工具）
    assert provider.call_idx > MAX_UNKNOWN_RUN


# ============================================================
# 场景 D：保序分批并发（AC8）
# ============================================================
@pytest.mark.asyncio
async def test_concurrent_batch_ordering() -> None:
    """两只读并发 + 一副作用串行 → 验证并发峰值和顺序。"""
    concurrent_peak = 0
    concurrent_counter = 0
    concurrency_lock = asyncio.Lock()

    read_start_times: list[float] = []
    read_end_times: list[float] = []
    write_start_time: float = 0.0

    async def read_execute(tool: FakeTool, args: str) -> Result:
        nonlocal concurrent_counter, concurrent_peak
        read_start_times.append(asyncio.get_event_loop().time())
        async with concurrency_lock:
            concurrent_counter += 1
            concurrent_peak = max(concurrent_peak, concurrent_counter)
        await asyncio.sleep(0.2)
        async with concurrency_lock:
            concurrent_counter -= 1
        read_end_times.append(asyncio.get_event_loop().time())
        return Result(f"read_{tool._name}")

    async def write_execute(tool: FakeTool, args: str) -> Result:
        nonlocal write_start_time
        write_start_time = asyncio.get_event_loop().time()
        return Result("written")

    registry = Registry()
    ro1 = FakeTool("read_file", read_only=True, execute_fn=read_execute)
    ro2 = FakeTool("glob", read_only=True, execute_fn=read_execute)
    rw = FakeTool("bash", read_only=False, execute_fn=write_execute)
    registry.register(ro1)
    registry.register(ro2)
    registry.register(rw)

    # 一轮返回 [ro, ro, rw]
    provider = FakeProvider(
        scripts=[
            [
                _text("doing work..."),
                StreamEvent(
                    tool_calls=[
                        ToolCall(
                            id="1", name="read_file", input=json.dumps({"path": "a"})
                        ),
                        ToolCall(
                            id="2", name="glob", input=json.dumps({"pattern": "*.py"})
                        ),
                        ToolCall(
                            id="3",
                            name="bash",
                            input=json.dumps({"command": "echo hi"}),
                        ),
                    ]
                ),
                _done(),
            ],
            [_text("done."), _done()],
        ]
    )

    session = Session()
    session.append("user", "read and write")

    # 消费事件流（副作用在 execute 中已记录）
    _events = [
        ev
        async for ev in Agent(provider, registry).run(
            session, Mode.NORMAL, asyncio.Event()
        )
    ]

    # 事件仍按调用序输出，兼容 TUI 的 FIFO 工具状态管理
    tool_events = [event.tool for event in _events if event.tool is not None]
    assert [(event.name, event.phase) for event in tool_events] == [
        ("read_file", Phase.START),
        ("glob", Phase.START),
        ("read_file", Phase.END),
        ("glob", Phase.END),
        ("bash", Phase.START),
        ("bash", Phase.END),
    ]
    # 两只读并发峰值应 ≥2
    assert concurrent_peak >= 2, f"expected concurrent_peak >= 2, got {concurrent_peak}"
    # rw 在两只读完成后才开始
    assert write_start_time > 0
    max_read_end = max(read_end_times) if read_end_times else 0
    assert write_start_time >= max_read_end - 0.05  # 容差
    # 结果按调用序写入历史
    tool_result_msg = session.messages[-2]  # 倒数第二是 tool results
    assert tool_result_msg.role == "tool"
    assert len(tool_result_msg.tool_results) == 3
    # 按序
    assert tool_result_msg.tool_results[0].tool_call_id == "1"
    assert tool_result_msg.tool_results[1].tool_call_id == "2"
    assert tool_result_msg.tool_results[2].tool_call_id == "3"


# ============================================================
# 场景 E：取消历史一致（AC9）
# ============================================================
@pytest.mark.asyncio
async def test_cancel_history_consistency() -> None:
    """取消后历史配对合法——有 tool_results、末尾 assistant。"""
    block_event = asyncio.Event()

    async def blocking_execute(tool: FakeTool, args: str) -> Result:
        block_event.set()
        await asyncio.sleep(1.0)
        return Result("never reached")

    registry = Registry()
    tool = FakeTool("read_file", read_only=True, execute_fn=blocking_execute)
    registry.register(tool)

    provider = FakeProvider(
        scripts=[
            [
                _text("reading..."),
                _tool_call("read_file", json.dumps({"path": "x"})),
                _done(),
            ],
        ]
    )

    session = Session()
    session.append("user", "read a file then I will cancel")

    cancel = asyncio.Event()

    async def run_and_cancel():
        events = []
        agent = Agent(provider, registry)
        async for ev in agent.run(session, Mode.NORMAL, cancel):
            events.append(ev)
            # 一旦工具开始执行（START 事件出现）就取消
            if ev.tool is not None and ev.tool.phase == Phase.START:
                cancel.set()
        return events

    _events = await run_and_cancel()

    # 历史末尾是 assistant 文本
    assert session.last_role() == "assistant"
    # 有 tool_results
    roles = [m.role for m in session.messages]
    assert "tool" in roles
    # 无悬空 tool_use（不含未配对的）
    # 可以继续对话
    provider2 = FakeProvider(
        scripts=[[_text("sorry about that."), _usage(), _done()]],
    )
    session.append("user", "continue")
    events2 = [
        ev
        async for ev in Agent(provider2, registry).run(
            session, Mode.NORMAL, asyncio.Event()
        )
    ]
    assert events2[-1].done
    assert any("sorry" in ev.text for ev in events2 if ev.text)


# ============================================================
# 场景 F：Plan 工具集（AC13）
# ============================================================
@pytest.mark.asyncio
async def test_plan_mode_restricts_tools() -> None:
    """Mode.PLAN → 工具定义仅含只读 + system_suffix == PLAN_MODE_REMINDER。"""
    registry = Registry()
    registry.register(FakeTool("read_file", read_only=True))
    registry.register(FakeTool("glob", read_only=True))
    registry.register(FakeTool("grep", read_only=True))
    registry.register(FakeTool("write_file", read_only=False))
    registry.register(FakeTool("edit_file", read_only=False))
    registry.register(FakeTool("bash", read_only=False))

    provider = FakeProvider(
        scripts=[[_text("plan here."), _usage(), _done()]],
        record_streams=True,
    )

    session = Session()
    session.append("user", "make a plan")

    events = [
        ev
        async for ev in Agent(provider, registry).run(
            session, Mode.PLAN, asyncio.Event()
        )
    ]

    assert provider.captured_defs
    tool_names = provider.captured_defs[0]
    # 仅含只读
    assert set(tool_names) == {"read_file", "glob", "grep"}
    # system_suffix 含 PLAN_MODE_REMINDER
    assert provider.captured_suffixes
    assert provider.captured_suffixes[0] == PLAN_MODE_REMINDER
    assert events[-1].done


# ============================================================
# 场景：流出错恢复（AC5）
# ============================================================
@pytest.mark.asyncio
async def test_stream_error_recovery() -> None:
    """provider 流出错 → err 事件 + 可继续对话。"""
    registry = Registry()
    tool = FakeTool()
    registry.register(tool)

    class ErrorProvider(FakeProvider):
        async def stream(self, session, tools=None, system_suffix=""):
            yield StreamEvent(text="starting...")
            raise RuntimeError("connection lost")

    provider = ErrorProvider(scripts=[])

    session = Session()
    session.append("user", "do something")

    events = [
        ev
        async for ev in Agent(provider, registry).run(
            session, Mode.NORMAL, asyncio.Event()
        )
    ]

    err_events = [ev for ev in events if ev.err is not None]
    assert err_events
    # 可继续对话
    assert session.last_role() == "assistant"
