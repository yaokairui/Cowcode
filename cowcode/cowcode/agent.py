"""ReAct 循环编排——Agent 自主多轮调用工具直到任务完成。"""

from __future__ import annotations

import asyncio
import json as _json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from cowcode.compact import (
    AutoCompactTrackingState,
    ContentReplacementState,
    RecoveryState,
    TriggerKind,
    manage_context,
    new_session_context,
)
from cowcode.compact.compact import ManageInput
from cowcode.compact.const import (
    AUTO_SAFETY_MARGIN,
    MANUAL_SAFETY_MARGIN,
    SUMMARY_RESERVE,
)
from cowcode.compact.token import estimate_tokens, usage_anchor
from cowcode.hook import DispatchResult, Event as HookEvent
from cowcode.hook.rule import Payload
from cowcode.permission import Decision, Engine, Mode, Outcome
from cowcode.prompt import PLAN_REMINDER_INTERVAL, plan_reminder
from cowcode.prompt import ActiveSkillEntry, render_active_skills_block
from cowcode.provider import Provider, PromptTooLongError, Request, SystemPrompt
from cowcode.memory import Manager as MemoryManager
from cowcode.runtime import SessionRuntime
from cowcode.session import (
    Message,
    Session,
    ToolCall,
    ToolDefinition,
    ToolResult,
    Usage,
)
from cowcode.tool import DEFAULT_TIMEOUT, Registry, truncate_text

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
    approval: "ApprovalRequest | None" = None
    compact: "CompactEvent | None" = None


class CompactPhase:
    """压缩生命周期阶段。"""

    BEFORE_AUTO = "before_auto"
    AFTER_AUTO = "after_auto"
    BEFORE_EMERGENCY = "before_emergency"
    AFTER_EMERGENCY = "after_emergency"


@dataclass
class CompactEvent:
    """上下文压缩状态事件。"""

    phase: str
    before: int = 0
    after: int = 0
    err: Exception | None = None


@dataclass
class AskUserEvent:
    """模型向用户发起澄清提问——TUI 应展示问题并等待回答。"""

    question: str
    options: list[str] = field(default_factory=list)
    tool_call_id: str = ""


@dataclass
class ApprovalRequest:
    """权限引擎判定为 Ask，Agent 暂停等待用户在回路批准。"""

    name: str
    args: str
    reason: str
    respond: asyncio.Future[Outcome] = field(default_factory=lambda: asyncio.Future())


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
    err: Exception | None = None


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
        engine: Engine | None = None,
        runtime: SessionRuntime | None = None,
        memory_manager: MemoryManager | None = None,
        allowed_tools: list[str] | None = None,
        hook_engine: object | None = None,
        max_turns: int = 0,
        permission_mode: Mode | None = None,
        dont_ask: bool = False,
        approval_upgrader: Callable[
            [ApprovalRequest], Awaitable[tuple[Outcome, bool]]
        ] | None = None,
        include_system_tools: bool = True,
        ctx: dict[str, Any] | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system_prompt = system_prompt
        self._environment = environment
        self._engine = engine
        if runtime is None:
            runtime = SessionRuntime(
                replacement=ContentReplacementState(),
                recovery=RecoveryState(),
                auto_tracking=AutoCompactTrackingState(),
                session=new_session_context("."),
            )
        self._runtime = runtime
        self._memory_manager = memory_manager
        self._hook_engine = hook_engine
        if hook_engine is not None:
            self._runtime.hook_engine = hook_engine
        self._allowed_tools = list(allowed_tools or [])
        self._max_turns = max_turns
        self._permission_mode = permission_mode
        self._dont_ask = dont_ask
        self._approval_upgrader = approval_upgrader
        self._include_system_tools = include_system_tools
        self._ctx = dict(ctx or {})
        self._run_lock = asyncio.Lock()

    def set_permission_mode(self, mode: Mode) -> None:
        self._permission_mode = mode

    def set_allowed_tools(self, allowed: list[str]) -> None:
        self._allowed_tools = list(allowed)

    def append_system_prompt(self, text: str) -> None:
        if not text:
            return
        self._system_prompt = (self._system_prompt.rstrip() + "\n\n" + text).strip()

    async def run(
        self,
        session: Session,
        mode: Mode = Mode.DEFAULT,
        cancel: asyncio.Event | None = None,
        mode_getter: Callable[[], Mode] | None = None,
    ) -> AsyncIterator[Event]:
        """执行 Agent Loop，yield Event 供 TUI 消费。"""
        if cancel is None:
            cancel = asyncio.Event()
        if mode_getter is None:
            mode_getter = lambda: mode

        async with self._run_lock:
            unknown_run = 0

            max_iterations = self._max_turns or MAX_ITERATIONS
            for it in range(1, max_iterations + 1):
                yield Event(iter=it)

                if cancel.is_set():
                    await self._finish_cancelled(session)
                    return

                current_mode = (
                    self._permission_mode
                    if self._permission_mode is not None
                    else mode_getter()
                )
                effective_mode_getter = lambda: (
                    self._permission_mode
                    if self._permission_mode is not None
                    else mode_getter()
                )
                definitions = (
                    self._registry.read_only_definitions()
                    if current_mode == Mode.PLAN
                    else self._registry.definitions()
                )
                if self._allowed_tools:
                    definitions = self._registry.definitions_filtered(
                        self._allowed_tools,
                        include_system=self._include_system_tools,
                    )
                definitions = self._filter_team_tools(definitions)
                reminder = ""
                if current_mode == Mode.PLAN:
                    full = it == 1 or (it - 1) % PLAN_REMINDER_INTERVAL == 0
                    reminder = plan_reminder(full)
                team_reminder = await self._ingest_team_mailbox()
                if team_reminder:
                    reminder = f"{reminder}\n\n{team_reminder}" if reminder else team_reminder
                reminder = await self._build_reminder(reminder)

                async with self._runtime.lock:
                    anchor = self._runtime.usage_anchor
                    anchor_len = self._runtime.anchor_msg_len
                    context_window = self._runtime.context_window
                estimated = estimate_tokens(anchor, session.get_history(), anchor_len)
                will_compact = (
                    estimated >= context_window - SUMMARY_RESERVE - AUTO_SAFETY_MARGIN
                )
                manage_input = ManageInput(
                    conv=session,
                    provider=self._provider,
                    context_window=context_window,
                    tool_defs=definitions,
                    replacement=self._runtime.replacement,
                    recovery=self._runtime.recovery,
                    auto_tracking=self._runtime.auto_tracking,
                    session=self._runtime.session,
                    usage_anchor=anchor,
                    anchor_msg_len=anchor_len,
                    estimated_token=estimated,
                    trigger=TriggerKind.AUTO,
                )
                if will_compact:
                    yield Event(compact=CompactEvent(CompactPhase.BEFORE_AUTO))
                try:
                    manage_output = await manage_context(manage_input)
                except Exception as exc:
                    if will_compact:
                        yield Event(
                            compact=CompactEvent(
                                CompactPhase.AFTER_AUTO,
                                before=estimated,
                                after=0,
                                err=exc,
                            )
                        )
                    yield Event(err=exc)
                    return
                if will_compact:
                    yield Event(
                        compact=CompactEvent(
                            CompactPhase.AFTER_AUTO,
                            before=manage_output.before_tokens,
                            after=manage_output.after_tokens,
                        )
                    )

                round_state = _RoundState()
                async for event in self._stream_once(
                    session, definitions, reminder, cancel, round_state
                ):
                    yield event

                text = round_state.text
                calls = round_state.calls
                usage = round_state.usage
                err = round_state.err

                if isinstance(err, PromptTooLongError):
                    yield Event(compact=CompactEvent(CompactPhase.BEFORE_EMERGENCY))
                    emergency_input = ManageInput(
                        conv=session,
                        provider=self._provider,
                        context_window=context_window,
                        tool_defs=definitions,
                        replacement=self._runtime.replacement,
                        recovery=self._runtime.recovery,
                        auto_tracking=self._runtime.auto_tracking,
                        session=self._runtime.session,
                        usage_anchor=anchor,
                        anchor_msg_len=anchor_len,
                        estimated_token=estimated,
                        trigger=TriggerKind.EMERGENCY,
                    )
                    try:
                        emergency_output = await manage_context(emergency_input)
                    except Exception as exc:
                        yield Event(
                            compact=CompactEvent(
                                CompactPhase.AFTER_EMERGENCY,
                                before=estimated,
                                after=0,
                                err=exc,
                            )
                        )
                        yield Event(err=exc)
                        return
                    yield Event(
                        compact=CompactEvent(
                            CompactPhase.AFTER_EMERGENCY,
                            before=emergency_output.before_tokens,
                            after=emergency_output.after_tokens,
                        )
                    )
                    async with self._runtime.lock:
                        self._runtime.usage_anchor = 0
                        self._runtime.anchor_msg_len = 0
                    if (
                        estimate_tokens(0, session.get_history(), 0)
                        >= context_window - MANUAL_SAFETY_MARGIN
                    ):
                        yield Event(err=err)
                        return
                    round_state = _RoundState()
                    async for event in self._stream_once(
                        session, definitions, reminder, cancel, round_state
                    ):
                        yield event
                    text = round_state.text
                    calls = round_state.calls
                    usage = round_state.usage
                    err = round_state.err

                if err is not None:
                    if cancel.is_set():
                        await self._finish_cancelled(session)
                        return
                    self._ensure_assistant_tail(session, NOTICE_STREAM_ERR)
                    yield Event(notice=NOTICE_STREAM_ERR)
                    yield Event(err=err)
                    yield Event(done=True)
                    return

                if usage is not None:
                    async with self._runtime.lock:
                        self._runtime.usage_anchor = usage_anchor(usage)
                        self._runtime.anchor_msg_len = session.length()
                    yield Event(usage=usage)

                if not calls:
                    final_text = self._ensure_final(text)
                    if not text.strip() and final_text != text:
                        yield Event(text=final_text)
                    session.append("assistant", final_text)
                    self._maybe_update_memory(session)
                    await self._dispatch_hook(HookEvent.STOP, {**self._base_payload(HookEvent.STOP), "iter": it})
                    yield Event(done=True)
                    return

                session.add_assistant_with_tool_calls(text, calls)
                unknown_run = unknown_run + 1 if self._all_unknown(calls) else 0

                execution_state = _ExecutionState()
                async for event in self._execute_batched(
                    calls, effective_mode_getter, cancel, execution_state
                ):
                    yield event
                session.add_tool_results(execution_state.results)

                if execution_state.paused_for_user:
                    return
                if not execution_state.completed:
                    self._ensure_assistant_tail(session, "（已取消）")
                    return
                if unknown_run >= MAX_UNKNOWN_RUN:
                    yield Event(notice=NOTICE_UNKNOWN_TOOLS)
                    self._ensure_assistant_tail(session, NOTICE_UNKNOWN_TOOLS)
                    yield Event(done=True)
                    return

            yield Event(notice=NOTICE_MAX_ITER)
            self._ensure_assistant_tail(session, NOTICE_MAX_ITER)
            yield Event(done=True)

    # ---------- 内部 ----------

    def _filter_team_tools(self, definitions: list[ToolDefinition]) -> list[ToolDefinition]:
        if self._allowed_tools:
            return definitions
        hidden = {"TaskCreate", "TaskGet", "TaskList", "TaskUpdate", "SendMessage"}
        return [definition for definition in definitions if definition.name not in hidden]

    async def _ingest_team_mailbox(self) -> str:
        from cowcode.agent_team_mailbox import ingest_team_mailbox

        return await ingest_team_mailbox(self, self._ctx)

    async def _build_reminder(self, base: str) -> str:
        prompts = await self._runtime.take_reminders()
        if not prompts:
            return base
        extra = "\n\n".join(prompts)
        return f"{base}\n\n{extra}" if base else extra

    async def _dispatch_hook(self, event: HookEvent, payload: Payload) -> DispatchResult:
        engine = self._hook_engine
        if engine is None:
            return DispatchResult()
        result = await engine.dispatch(event, payload)
        await self._runtime.append_reminders(result.injected_prompts)
        return result

    def _base_payload(self, event: HookEvent) -> Payload:
        return {
            "event": event.value,
            "session_id": self._runtime.session.session_id,
            "cwd": str(Path(self._runtime.session.session_dir).parent.parent.parent),
            "mode": "",
        }

    async def _stream_once(
        self,
        session: Session,
        definitions: list[ToolDefinition],
        reminder: str,
        cancel: asyncio.Event,
        state: _RoundState,
    ) -> AsyncIterator[Event]:
        """单轮流式收集；事件实时转发，最终值写入 state。"""
        payload = self._base_payload(HookEvent.PRE_USER_MESSAGE)
        last_user = next(
            (m.content for m in reversed(session.get_history()) if m.role == "user"), ""
        )
        payload["prompt"] = last_user
        await self._dispatch_hook(HookEvent.PRE_USER_MESSAGE, payload)
        reminder = await self._build_reminder(reminder)
        request = Request(
            messages=session.get_history(),
            tools=list(definitions),
            system=SystemPrompt(
                stable=self._system_prompt,
                environment=self._render_environment(),
            ),
            reminder=reminder,
        )
        try:
            async for ev in self._provider.stream(request):
                if cancel.is_set():
                    state.err = asyncio.CancelledError()
                    return
                if ev.err is not None:
                    state.err = ev.err
                    return
                if ev.usage is not None:
                    state.usage = ev.usage
                if ev.tool_calls:
                    state.calls.extend(ev.tool_calls)
                if ev.text:
                    state.text += ev.text
                    yield Event(text=ev.text)
        except Exception as exc:
            state.err = exc
            return

        if cancel.is_set():
            state.err = asyncio.CancelledError()

    def _render_environment(self) -> str:
        """每轮请求前拼接动态激活的 Skill SOP。"""

        entries = [
            ActiveSkillEntry(entry.name, entry.body)
            for entry in self._runtime.active_skills.snapshot()
        ]
        skills_block = render_active_skills_block(entries)
        if not skills_block:
            return self._environment
        if not self._environment.strip():
            return skills_block
        return self._environment.rstrip() + "\n\n" + skills_block

    async def _pre_tool_hook_result(self, call: ToolCall) -> ToolResult | None:
        payload = self._base_payload(HookEvent.PRE_TOOL_USE)
        payload["tool_name"] = call.name
        payload["tool_input"] = self._tool_input_payload(call)
        result = await self._dispatch_hook(HookEvent.PRE_TOOL_USE, payload)
        if not result.blocked:
            return None
        return ToolResult(
            tool_call_id=call.id,
            content=f"[hook {result.blocking_hook_name}] {result.reason}",
            is_error=True,
        )

    async def _post_tool_hook(self, call: ToolCall, result: ToolResult) -> None:
        payload = self._base_payload(HookEvent.POST_TOOL_USE)
        payload["tool_name"] = call.name
        payload["tool_input"] = self._tool_input_payload(call)
        payload["tool_result"] = result.content
        payload["is_error"] = result.is_error
        await self._dispatch_hook(HookEvent.POST_TOOL_USE, payload)

    @staticmethod
    def _tool_input_payload(call: ToolCall) -> object:
        try:
            return _json.loads(call.input or "{}")
        except Exception:
            return call.input or ""

    async def _execute_batched(
        self,
        calls: list[ToolCall],
        mode_getter: Callable[[], Mode],
        cancel: asyncio.Event,
        state: _ExecutionState,
    ) -> AsyncIterator[Event]:
        """保序分批并发执行工具；权限检查接入五层流水线。

        AskUserQuestion 被特殊拦截；Read 工具先 engine.check 再并发；
        Write/Exec 工具先 engine.check，Ask 时走人在回路审批。
        """
        results: list[ToolResult | None] = [None] * len(calls)
        engine = self._engine

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
                # 并发批 [i, j) -- 只读工具
                # ① 权限检查每个 call，DENY 预填结果不纳入 gather
                deny_indices: set[int] = set()
                for k in range(i, j):
                    blocked = await self._pre_tool_hook_result(calls[k])
                    if blocked is not None:
                        results[k] = blocked
                        deny_indices.add(k)
                        continue
                    if engine is not None:
                        decision, reason = engine.check(mode_getter(), calls[k], True)
                        if decision == Decision.DENY:
                            results[k] = ToolResult(
                                tool_call_id=calls[k].id,
                                content=reason,
                                is_error=True,
                            )
                            deny_indices.add(k)
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
                # 只 run 未被 deny 的
                gather_indices = [k for k in range(i, j) if k not in deny_indices]
                if gather_indices:

                    async def _gather_one(k: int) -> None:
                        results[k] = await self._run_one(calls[k])
                        await self._record_read_file(calls[k], results[k])

                    await asyncio.gather(*(_gather_one(k) for k in gather_indices))
                for k in range(i, j):
                    result = results[k]
                    if result is None:
                        result = ToolResult(
                            tool_call_id=calls[k].id,
                            content=NOTICE_CANCELLED,
                            is_error=True,
                        )
                        results[k] = result
                    await self._post_tool_hook(calls[k], result)
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
                # 串行执行单个 —— Write/Exec 工具
                call = calls[i]
                outcome = Outcome.ALLOW_ONCE  # default: allow if no engine
                decision = Decision.ALLOW
                reason = ""
                blocked = await self._pre_tool_hook_result(call)
                if blocked is not None:
                    results[i] = blocked
                    yield Event(
                        tool=ToolEvent(
                            name=call.name,
                            args=self._args_preview(call.input or "{}"),
                            phase=Phase.START,
                        )
                    )
                    yield Event(
                        tool=ToolEvent(
                            name=call.name,
                            args=self._args_preview(call.input or "{}"),
                            phase=Phase.END,
                            result=blocked.content,
                            is_error=True,
                        )
                    )
                    i += 1
                    continue
                if engine is not None:
                    decision, reason = engine.check(mode_getter(), call, False)

                if decision == Decision.DENY:
                    results[i] = ToolResult(
                        tool_call_id=call.id, content=reason, is_error=True
                    )
                    yield Event(
                        tool=ToolEvent(
                            name=call.name,
                            args=self._args_preview(call.input or "{}"),
                            phase=Phase.START,
                        )
                    )
                    yield Event(
                        tool=ToolEvent(
                            name=call.name,
                            args=self._args_preview(call.input or "{}"),
                            phase=Phase.END,
                            result=results[i].content,
                            is_error=True,
                        )
                    )
                    i += 1
                    continue

                if decision == Decision.ASK:
                    yield Event(
                        tool=ToolEvent(
                            name=call.name,
                            args=self._args_preview(call.input or "{}"),
                            phase=Phase.START,
                        )
                    )
                    if self._dont_ask:
                        outcome = Outcome.ALLOW_ONCE
                    else:
                        respond: asyncio.Future[Outcome] = asyncio.Future()
                        req = ApprovalRequest(
                            name=call.name,
                            args=self._args_preview(call.input or "{}"),
                            reason=reason,
                            respond=respond,
                        )
                        if self._approval_upgrader is not None:
                            upgraded, ok = await self._approval_upgrader(req)
                            if ok:
                                outcome = upgraded
                            else:
                                yield Event(approval=req)
                                try:
                                    outcome = await respond
                                except asyncio.CancelledError:
                                    results[i] = ToolResult(
                                        tool_call_id=call.id,
                                        content=NOTICE_CANCELLED,
                                        is_error=True,
                                    )
                                    yield Event(
                                        tool=ToolEvent(
                                            name=call.name,
                                            args=self._args_preview(call.input or "{}"),
                                            phase=Phase.END,
                                            result=results[i].content,
                                            is_error=True,
                                        )
                                    )
                                    state.results = self._coalesce_results(results)
                                    state.completed = False
                                    return
                        else:
                            yield Event(approval=req)
                            try:
                                outcome = await respond
                            except asyncio.CancelledError:
                                results[i] = ToolResult(
                                    tool_call_id=call.id,
                                    content=NOTICE_CANCELLED,
                                    is_error=True,
                                )
                                yield Event(
                                    tool=ToolEvent(
                                        name=call.name,
                                        args=self._args_preview(call.input or "{}"),
                                        phase=Phase.END,
                                        result=results[i].content,
                                        is_error=True,
                                    )
                                )
                                state.results = self._coalesce_results(results)
                                state.completed = False
                                return

                    if outcome == Outcome.DENY_ONCE:
                        results[i] = ToolResult(
                            tool_call_id=call.id,
                            content=f"用户拒绝了执行：{call.name}",
                            is_error=True,
                        )
                        yield Event(
                            tool=ToolEvent(
                                name=call.name,
                                args=self._args_preview(call.input or "{}"),
                                phase=Phase.END,
                                result=results[i].content,
                                is_error=True,
                            )
                        )
                        i += 1
                        continue

                    if outcome == Outcome.ALLOW_FOREVER and engine is not None:
                        try:
                            from cowcode.permission import persist_local_allow

                            persist_local_allow(engine, call)
                        except Exception:
                            pass  # 写规则失败不阻断执行

                # 执行（ALLOW / ALLOW_ONCE / ALLOW_FOREVER）
                if decision != Decision.ASK:
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
                await self._record_read_file(call, results[i])
                await self._post_tool_hook(call, results[i])
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

    async def run_force_compact(
        self,
        session: Session,
        tool_defs: list[ToolDefinition] | None = None,
    ) -> tuple[int, int]:
        """手动触发一次上下文压缩。"""

        async with self._run_lock:
            if tool_defs is None:
                tool_defs = self._registry.definitions()
            async with self._runtime.lock:
                anchor = self._runtime.usage_anchor
                anchor_len = self._runtime.anchor_msg_len
                context_window = self._runtime.context_window
            estimated = estimate_tokens(anchor, session.get_history(), anchor_len)
            out = await manage_context(
                ManageInput(
                    conv=session,
                    provider=self._provider,
                    context_window=context_window,
                    tool_defs=tool_defs,
                    replacement=self._runtime.replacement,
                    recovery=self._runtime.recovery,
                    auto_tracking=self._runtime.auto_tracking,
                    session=self._runtime.session,
                    usage_anchor=anchor,
                    anchor_msg_len=anchor_len,
                    estimated_token=estimated,
                    trigger=TriggerKind.MANUAL,
                )
            )
            async with self._runtime.lock:
                self._runtime.usage_anchor = 0
                self._runtime.anchor_msg_len = 0
            return out.before_tokens, out.after_tokens

    async def _record_read_file(
        self, call: ToolCall, result: ToolResult | None
    ) -> None:
        """ReadFile 成功后记录纯净文件内容。"""

        if result is None or result.is_error or call.name != "read_file":
            return
        try:
            data = _json.loads(call.input or "{}")
        except Exception:
            return
        path_value = data.get("path") if isinstance(data, dict) else None
        if not isinstance(path_value, str) or not path_value:
            return
        try:
            abs_path = Path(path_value).resolve()
            raw = await asyncio.to_thread(abs_path.read_bytes)
        except OSError:
            return
        self._runtime.recovery.record_file(
            str(abs_path), raw.decode("utf-8", errors="replace")
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

    def _maybe_update_memory(self, session: Session) -> None:
        mem_mgr = self._memory_manager
        if mem_mgr is None:
            return
        history = session.get_history()
        recent = self._recent_turn(history)
        self._runtime.turn_count += 1
        if self._runtime.turn_count % 5 != 0 and not _has_memory_signal(recent):
            return
        asyncio.create_task(mem_mgr.update_async(recent))

    @staticmethod
    def _recent_turn(history: list[Message]) -> list[Message]:
        for index in range(len(history) - 1, -1, -1):
            if history[index].role == "user":
                return history[index:]
        return history[-2:]

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


def _has_memory_signal(messages: list[Message]) -> bool:
    text = "\n".join(msg.content for msg in messages if msg.role == "user").lower()
    return any(
        keyword in text for keyword in ("记住", "记忆", "别忘", "remember", "memo")
    )
