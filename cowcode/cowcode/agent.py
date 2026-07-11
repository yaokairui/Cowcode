"""ReAct 循环编排——Agent 自主多轮调用工具直到任务完成。"""

from __future__ import annotations

import asyncio
import json as _json
from dataclasses import dataclass, field
from enum import IntEnum
from typing import AsyncIterator

from cowcode.prompt import PLAN_REMINDER_INTERVAL, plan_reminder
from cowcode.provider import Provider, Request, SystemPrompt
from cowcode.session import Session, ToolCall, ToolDefinition, ToolResult, Usage
from cowcode.tool import DEFAULT_TIMEOUT, Registry, truncate_text

# ----- 枚举 -----


class Mode(IntEnum):
    NORMAL = 0
    PLAN = 1


# ----- 常量 -----
MAX_ITERATIONS: int = 25
MAX_UNKNOWN_RUN: int = 3

# 停止/收尾提示文案
NOTICE_MAX_ITER = "（已达最大迭代轮数 25，自动停止；可继续发消息推进。）"
NOTICE_UNKNOWN_TOOLS = "（连续多轮只请求到未注册的工具，自动停止。）"
NOTICE_STREAM_ERR = "（请求出错，本轮已中断。）"
NOTICE_CANCELLED = "（已取消。）"


# ----- 事件 -----
@dataclass
class Event:
    """Agent 对外事件流元素。"""

    text: str = ""
    tool: "ToolEvent | None" = None
    usage: Usage | None = None
    iter: int = 0
    notice: str = ""
    done: bool = False
    err: Exception | None = None
    ask_user: "AskUserEvent | None" = None


@dataclass
class AskUserEvent:
    """模型向用户发起澄清提问——TUI 应展示问题并等待回答。"""

    question: str
    options: list[str] = field(default_factory=list)
    tool_call_id: str = ""


class Phase:
    """工具执行阶段标记。"""

    START = "start"
    END = "end"


@dataclass
class ToolEvent:
    """UI 可渲染的工具执行事件。"""

    name: str
    args: str = ""
    phase: str = Phase.START
    result: str = ""
    is_error: bool = False


@dataclass
class _RoundState:
    """单次 Provider 请求的聚合状态。"""

    text: str = ""
    calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    ok: bool = True


@dataclass
class _ExecutionState:
    """一批工具调用的聚合状态。"""

    results: list[ToolResult] = field(default_factory=list)
    completed: bool = True
    paused_for_user: bool = False


# ----- Agent -----
class Agent:
    """ReAct 循环编排器——执行多轮「思考→调工具→回灌结果」直到任务完成。"""

    def __init__(
        self,
        provider: Provider,
        registry: Registry,
        system_prompt: str = "",
        environment: str = "",
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system_prompt = system_prompt
        self._environment = environment

    async def run(
        self,
        session: Session,
        mode: Mode = Mode.NORMAL,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[Event]:
        """执行 Agent Loop，yield Event 供 TUI 消费。"""
        if cancel is None:
            cancel = asyncio.Event()

        # 按 mode 确定工具集；稳定系统提示跨模式不变
        if mode == Mode.PLAN:
            definitions = self._registry.read_only_definitions()
        else:
            definitions = self._registry.definitions()

        unknown_run = 0

        for it in range(1, MAX_ITERATIONS + 1):
            yield Event(iter=it)

            if cancel.is_set():
                await self._finish_cancelled(session)
                return

            reminder = ""
            if mode == Mode.PLAN:
                full = it == 1 or (it - 1) % PLAN_REMINDER_INTERVAL == 0
                reminder = plan_reminder(full)

            # ----- 一轮流式收集 -----
            round_state = _RoundState()
            async for event in self._stream_once(
                session, definitions, reminder, cancel, round_state
            ):
                yield event

            text = round_state.text
            calls = round_state.calls
            usage = round_state.usage
            if not round_state.ok:
                if cancel.is_set():
                    await self._finish_cancelled(session)
                    return
                self._ensure_assistant_tail(session, NOTICE_STREAM_ERR)
                yield Event(notice=NOTICE_STREAM_ERR)
                yield Event(done=True)
                return

            # ----- 用量 -----
            if usage is not None:
                yield Event(usage=usage)

            # ----- 无工具：自然完成 -----
            if not calls:
                final_text = self._ensure_final(text)
                if not text.strip() and final_text != text:
                    yield Event(text=final_text)
                session.append("assistant", final_text)
                yield Event(done=True)
                return

            # ----- 有工具：写入历史 -----
            session.add_assistant_with_tool_calls(text, calls)

            # 统计连续未知工具
            if self._all_unknown(calls):
                unknown_run += 1
            else:
                unknown_run = 0

            # 保序分批执行
            execution_state = _ExecutionState()
            async for event in self._execute_batched(calls, cancel, execution_state):
                yield event

            session.add_tool_results(execution_state.results)

            # AskUserQuestion 暂停：退出循环，等待 CLI 以回答重启
            if execution_state.paused_for_user:
                return

            # 取消：最高优先级终止
            if not execution_state.completed:
                self._ensure_assistant_tail(session, "（已取消）")
                return

            # 连续未知工具停止
            if unknown_run >= MAX_UNKNOWN_RUN:
                yield Event(notice=NOTICE_UNKNOWN_TOOLS)
                self._ensure_assistant_tail(session, NOTICE_UNKNOWN_TOOLS)
                yield Event(done=True)
                return

        # 循环走完——触达迭代上限
        yield Event(notice=NOTICE_MAX_ITER)
        self._ensure_assistant_tail(session, NOTICE_MAX_ITER)
        yield Event(done=True)

    # ---------- 内部 ----------

    async def _stream_once(
        self,
        session: Session,
        definitions: list[ToolDefinition],
        reminder: str,
        cancel: asyncio.Event,
        state: _RoundState,
    ) -> AsyncIterator[Event]:
        """单轮流式收集；事件实时转发，最终值写入 state。"""
        request = Request(
            messages=session.get_history(),
            tools=list(definitions),
            system=SystemPrompt(
                stable=self._system_prompt,
                environment=self._environment,
            ),
            reminder=reminder,
        )
        try:
            async for ev in self._provider.stream(request):
                if cancel.is_set():
                    state.ok = False
                    return
                if ev.err is not None:
                    state.ok = False
                    yield Event(err=ev.err)
                    return
                if ev.usage is not None:
                    state.usage = ev.usage
                if ev.tool_calls:
                    state.calls.extend(ev.tool_calls)
                if ev.text:
                    state.text += ev.text
                    yield Event(text=ev.text)
        except Exception as exc:
            state.ok = False
            yield Event(err=exc)
            return

        if cancel.is_set():
            state.ok = False

    async def _execute_batched(
        self,
        calls: list[ToolCall],
        cancel: asyncio.Event,
        state: _ExecutionState,
    ) -> AsyncIterator[Event]:
        """保序分批并发执行工具；START/END 事件实时转发。

        AskUserQuestion 被特殊拦截：发出 ask_user 事件、写入等待结果后，
        本轮循环终止，由 CLI 收集用户回答后重新启动 Agent。
        """
        results: list[ToolResult | None] = [None] * len(calls)

        i = 0
        while i < len(calls):
            if cancel.is_set():
                self._fill_cancelled_results(calls, results, i)
                state.results = self._coalesce_results(results)
                state.completed = False
                return

            call = calls[i]

            # ----- AskUserQuestion 拦截 -----
            if call.name == "AskUserQuestion":
                yield Event(
                    tool=ToolEvent(
                        name=call.name,
                        args=self._args_preview(call.input or "{}"),
                        phase=Phase.START,
                    )
                )
                question, options = self._parse_ask_user_input(call.input or "{}")
                results[i] = ToolResult(
                    tool_call_id=call.id,
                    content=f"Question: {question}",
                    is_error=False,
                )
                state.results = self._coalesce_results(results)
                state.completed = True
                state.paused_for_user = True
                yield Event(
                    tool=ToolEvent(
                        name=call.name,
                        args=self._args_preview(call.input or "{}"),
                        phase=Phase.END,
                        result=results[i].content,
                        is_error=False,
                    )
                )
                yield Event(
                    ask_user=AskUserEvent(
                        question=question,
                        options=options,
                        tool_call_id=call.id,
                    )
                )
                # 本轮结束——CLI 收到 ask_user 后应重启 Agent
                return
            # ----- 常规工具继续 -----

            # 向前吃连续只读
            j = i
            while j < len(calls) and self._registry.is_read_only(calls[j].name):
                j += 1

            if j > i:
                # 并发批 [i, j)
                for k in range(i, j):
                    yield Event(
                        tool=ToolEvent(
                            name=calls[k].name,
                            args=self._args_preview(calls[k].input or "{}"),
                            phase=Phase.START,
                        )
                    )
                if cancel.is_set():
                    self._fill_cancelled_results(calls, results, i)
                    state.results = self._coalesce_results(results)
                    state.completed = False
                    return
                await self._run_concurrent_batch(calls, i, j, results, cancel)
                for k in range(i, j):
                    result = results[k]
                    if result is None:
                        result = ToolResult(
                            tool_call_id=calls[k].id,
                            content=NOTICE_CANCELLED,
                            is_error=True,
                        )
                        results[k] = result
                    yield Event(
                        tool=ToolEvent(
                            name=calls[k].name,
                            args=self._args_preview(calls[k].input or "{}"),
                            phase=Phase.END,
                            result=result.content,
                            is_error=result.is_error,
                        )
                    )
                i = j
            else:
                # 串行执行单个
                call = calls[i]
                yield Event(
                    tool=ToolEvent(
                        name=call.name,
                        args=self._args_preview(call.input or "{}"),
                        phase=Phase.START,
                    )
                )
                if cancel.is_set():
                    self._fill_cancelled_results(calls, results, i)
                    state.results = self._coalesce_results(results)
                    state.completed = False
                    return
                results[i] = await self._run_one(call)
                yield Event(
                    tool=ToolEvent(
                        name=call.name,
                        args=self._args_preview(call.input or "{}"),
                        phase=Phase.END,
                        result=results[i].content,
                        is_error=results[i].is_error,
                    )
                )
                i += 1

        state.results = self._coalesce_results(results)
        state.completed = not cancel.is_set()

    async def _run_concurrent_batch(
        self,
        calls: list[ToolCall],
        start: int,
        end: int,
        results: list[ToolResult | None],
        cancel: asyncio.Event,
    ) -> None:
        """并发执行 [start, end) 区间的只读工具。每个 task 只写自己下标。"""

        async def _one(k: int) -> None:
            if cancel.is_set():
                results[k] = ToolResult(
                    tool_call_id=calls[k].id,
                    content=NOTICE_CANCELLED,
                    is_error=True,
                )
                return
            results[k] = await self._run_one(calls[k])

        await asyncio.gather(*(_one(k) for k in range(start, end)))

    async def _run_one(self, call: ToolCall) -> ToolResult:
        """执行单个工具，带超时。"""
        try:
            result = await asyncio.wait_for(
                self._registry.execute(call.name, call.input or "{}"),
                timeout=DEFAULT_TIMEOUT,
            )
            return ToolResult(
                tool_call_id=call.id,
                content=result.content,
                is_error=result.is_error,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool_call_id=call.id,
                content=f"Tool {call.name} timed out after {DEFAULT_TIMEOUT:.1f}s",
                is_error=True,
            )

    # ---------- 辅助 ----------

    def _all_unknown(self, calls: list[ToolCall]) -> bool:
        """全部调用都是未注册工具？全 None 才 True。"""
        return all(self._registry.get(call.name) is None for call in calls)

    def _ensure_final(self, text: str) -> str:
        """确保 assistant 文本非空。"""
        if text.strip():
            return text
        return (
            "Tool results were returned, but the model did not provide a final answer."
        )

    def _ensure_assistant_tail(self, session: Session, fallback: str) -> None:
        """如果最后一条不是 assistant，补一条 fallback 文本，保证角色交替合法。"""
        if session.last_role() != "assistant":
            session.append("assistant", fallback)

    async def _finish_cancelled(self, session: Session) -> None:
        """取消收尾——保证历史以 assistant 文本结尾。"""
        self._ensure_assistant_tail(session, NOTICE_CANCELLED)

    @staticmethod
    def _args_preview(raw: str, max_chars: int = 180) -> str:
        """截断参数预览。"""
        return truncate_text(raw, max_lines=3, max_chars=max_chars)

    @staticmethod
    def _fill_cancelled_results(
        calls: list[ToolCall],
        results: list[ToolResult | None],
        start: int,
    ) -> None:
        """为尚未执行的调用补齐取消结果，保持 tool call 配对。"""
        for index in range(start, len(calls)):
            if results[index] is None:
                results[index] = ToolResult(
                    tool_call_id=calls[index].id,
                    content=NOTICE_CANCELLED,
                    is_error=True,
                )

    @staticmethod
    def _coalesce_results(results: list[ToolResult | None]) -> list[ToolResult]:
        """将可能含 None 的 result 列表合并为全量 ToolResult。"""
        return [
            r
            if r is not None
            else ToolResult(tool_call_id="", content="(no result)", is_error=True)
            for r in results
        ]

    @staticmethod
    def _parse_ask_user_input(raw: str) -> tuple[str, list[str]]:
        """从 AskUserQuestion 的 JSON args 中提取 question 和 options。"""
        try:
            data = _json.loads(raw)
        except Exception:
            return raw, []
        question = data.get("question", raw) if isinstance(data, dict) else raw
        options = data.get("options") if isinstance(data, dict) else None
        if isinstance(options, list) and all(isinstance(o, str) for o in options):
            return str(question), options  # type: ignore[arg-type]
        return str(question), []
