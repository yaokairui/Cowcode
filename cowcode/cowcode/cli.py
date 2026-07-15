"""Textual TUI for Cowcode."""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Footer, OptionList, RichLog, Static, TextArea
from textual.widgets._option_list import Option

from cowcode import __version__, coordinator
from cowcode.agent import (
    Agent,
    ApprovalRequest,
    AskUserEvent,
    CompactEvent,
    CompactPhase,
    Phase,
)
from cowcode.command import Kind, Registry as CommandRegistry, parse, register_builtins
from cowcode.command import SkillSummary, WorktreeAccessor, register_skills_as_commands, remove_skill_commands
from cowcode.completion import CompletionMenu
from cowcode.config import (
    Config,
    ConfigError,
    ProviderConfig,
    effective_context_window,
    load_configs,
    resolve_config_path,
)
from cowcode.agent_tool import AgentTool
from cowcode.environment import gather_environment
from cowcode.tool.ctx import with_cwd
from cowcode.worktree_adapter import WorktreeAdapter
from cowcode import worktree
from cowcode import hook, mcp as mcp_client
from cowcode.hook import Event as HookEvent
from cowcode.hook.rule import Rule as HookRule
from cowcode.permission import Engine, Mode, Outcome, new_engine
from cowcode.prompt import build_system_prompt
from cowcode.prompt import SkillCatalogItem, render_skills_catalog
from cowcode.provider import Provider, create_provider
from cowcode.runtime import SessionRuntime
from cowcode.skills import Catalog
from cowcode.skills.executor import Executor
from cowcode.tool.install_skill import InstallSkillTool
from cowcode.tool.load_skill import LoadSkillTool
from cowcode.session import (
    Message,
    Session,
    SessionInfo,
    Writer,
    clean_expired,
    last_message_ts,
    list_sessions,
    load_session,
)
from cowcode.instructions import Loader as InstructionsLoader
from cowcode.memory import Manager as MemoryManager
from cowcode.tool import Registry, new_default_registry, truncate_text
from cowcode.subagent import load_catalog as load_subagent_catalog
from cowcode.task_manager import Manager as TaskManager
from cowcode.task_notice import consume_task_done
from cowcode.task_tools import TaskGetTool as BgTaskGetTool
from cowcode.task_tools import TaskListTool as BgTaskListTool
from cowcode.task_tools import TaskStopTool
from cowcode.compact import (
    AutoCompactTrackingState,
    ContentReplacementState,
    RecoveryState,
    new_session_context,
    open_session_context,
)
from cowcode.compact.const import AUTO_SAFETY_MARGIN, SUMMARY_RESERVE
from cowcode.compact.token import estimate_tokens

__all__ = ["CowcodeApp", "main"]

_CONTEXT_COLLAPSED_H = 4
_CONTEXT_EXPANDED_H = 12


@dataclass
class ResumeState:
    """会话恢复列表状态。"""

    items: list[SessionInfo]
    filtered: list[SessionInfo]
    query: str = ""
    selected: int = 0


CAT_BANNER = r"""
   ____                              _
  / ___| _____      _____ ___   __| | ___
 | |    / _ \ \ /\ / / __/ _ \ / _` |/ _ \
 | |___| (_) \ V  V / (_| (_) | (_| |  __/
  \____|\___/ \_/\_/ \___\___/ \__,_|\___|
"""


def _compact_tok(n: int) -> str:
    """紧凑 token 数字。"""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _format_mcp_status(server_count: int, tool_count: int) -> str:
    return f"Connected to {server_count} MCP server(s), {tool_count} tools registered"


def format_compact_notice(event: CompactEvent) -> str:
    """统一格式化压缩状态提示。"""

    if event.phase == CompactPhase.BEFORE_AUTO:
        return "⟳ Compacting conversation..."
    if event.phase == CompactPhase.BEFORE_EMERGENCY:
        return "⟳ Context limit hit, compacting conversation..."
    if event.err is not None:
        return f"✗ Compact failed: {event.err}"
    arrow = "↓" if event.after <= event.before else "↑"
    note = "" if event.after <= event.before else "（压缩摘要与恢复段比原文更长）"
    return f"◉ Compacted: {event.before} → {event.after} estimated tokens {arrow}{note}"


def _format_relative_time(value: datetime) -> str:
    seconds = max(0, int((datetime.now() - value).total_seconds()))
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hours ago"
    days = hours // 24
    return f"{days} days ago"


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f}MB"
    if size >= 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size}B"


def _format_session_item(info: SessionInfo) -> str:
    model = info.model or "unknown-model"
    return f"{info.title} · {_format_relative_time(info.modified_at)} · {model} · {_format_size(info.size)}"


class ToolDisplay:
    """动态区展示的单个在跑工具。"""

    def __init__(self, name: str, args: str) -> None:
        self.name = name
        self.args = args


class ContextHeader(Static):
    """固定在对话区上方，显示当前问题，长问题可折叠。"""

    def __init__(self, max_lines_collapsed: int = 3) -> None:
        super().__init__(Text(""), id="context-header")
        self._full_text = ""
        self._expanded = False
        self._max_lines = max_lines_collapsed

    def set_context(self, text: str) -> None:
        self._full_text = text.strip()
        self._expanded = False
        self._update_display()

    def clear_context(self) -> None:
        self._full_text = ""
        self._expanded = False
        self.styles.height = 0
        self.update(Text(""))

    def render(self) -> Text:
        rendered = super().render()
        if rendered is None:
            return Text("")
        if isinstance(rendered, Text):
            return rendered
        return Text.from_markup(str(rendered))

    def toggle_context(self) -> None:
        if not self._full_text:
            return
        if len(self._full_text.splitlines()) <= self._max_lines:
            return
        self._expanded = not self._expanded
        self._update_display()

    def _update_display(self) -> None:
        if not self._full_text:
            self.clear_context()
            return

        lines = self._full_text.splitlines() or [self._full_text]
        is_long = len(lines) > self._max_lines
        if is_long and not self._expanded:
            truncated = "\n".join(lines[: self._max_lines])
            more_count = len(lines) - self._max_lines
            body = (
                "[bold]Current question:[/]\n"
                f"{truncated}\n"
                f"[dim]... {more_count} more lines (Ctrl+T)[/]"
            )
            self.styles.height = _CONTEXT_COLLAPSED_H
        else:
            body = f"[bold]Current question:[/]\n{self._full_text}"
            self.styles.height = _CONTEXT_EXPANDED_H if is_long else len(lines) + 1
        self.update(body)


class ProviderSelectScreen(Screen[str]):
    """Provider 选择界面。"""

    def __init__(self, providers: list[ProviderConfig]) -> None:
        super().__init__()
        self._providers = providers

    def compose(self) -> ComposeResult:
        option_list = OptionList(id="provider-list")
        for index, provider in enumerate(self._providers):
            option_list.add_option(
                Option(
                    f"{provider.name}  -  {provider.model} ({provider.protocol})",
                    id=str(index),
                )
            )
        yield option_list

    def on_mount(self) -> None:
        self.query_one("#provider-list", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(str(event.option_id))


class AskUserQuestionScreen(Screen[str]):
    """澄清问题弹窗——展示问题 + 可选项列表 + 自定义输入。"""

    def __init__(self, question: str, options: list[str]) -> None:
        super().__init__()
        self._question = question
        self._options = options

    def compose(self) -> ComposeResult:
        yield Static(
            Text(f"❓ {self._question}", style="bold yellow"),
            id="ask-question",
        )
        option_list = OptionList(id="ask-options")
        for index, opt in enumerate(self._options):
            option_list.add_option(Option(opt, id=str(index)))
        yield option_list
        yield TextArea(
            "",
            id="ask-custom",
            placeholder="Or type your own answer… (Alt+Enter to submit)",
            show_line_numbers=False,
        )

    def on_mount(self) -> None:
        self.query_one("#ask-options", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        opt_index = int(event.option_id)
        if 0 <= opt_index < len(self._options):
            self.dismiss(self._options[opt_index])

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        text = event.text_area.text
        if text.endswith("\n"):
            clean = text.strip()
            if clean:
                event.text_area.text = ""
                self.dismiss(clean)


class MessageInput(TextArea):
    """处理消息输入框的发送和换行快捷键。"""

    BINDINGS = [
        Binding("enter", "submit_message", show=False, priority=True),
        Binding("alt+enter", "insert_newline", show=False, priority=True),
    ]

    def action_submit_message(self) -> None:
        app = self.app
        if isinstance(app, CowcodeApp):
            app.run_worker(app._handle_send(), exclusive=True)

    def action_insert_newline(self) -> None:
        self.insert("\n")


class CowcodeApp(App[Any]):
    """Cowcode 主 TUI 应用。"""

    BINDINGS = [
        Binding("escape", "cancel_or_quit", "Cancel/Quit"),
        Binding("ctrl+c", "cancel_or_quit", "Cancel/Quit"),
        Binding("ctrl+t", "toggle_context", "Context"),
        Binding("f2", "cycle_mode", "Mode"),
    ]

    CSS = """
    #banner {
        width: 100%;
        height: auto;
        content-align: center middle;
        margin-bottom: 1;
        padding: 1;
        color: $accent;
        text-style: bold;
    }

    #context-header {
        width: 100%;
        height: 0;
        padding: 0 1;
        margin-bottom: 0;
        background: $boost;
        color: $text;
    }

    #conversation {
        width: 100%;
        height: 1fr;
        margin-bottom: 1;
    }

    #streaming-response {
        width: 100%;
        min-height: 0;
        max-height: 10;
        padding: 0 1;
        color: $text;
    }

    #timer {
        height: 1;
        padding: 0 1;
        color: $text-muted;
        text-style: italic;
    }

    #input-box {
        width: 100%;
        height: 5;
        min-height: 3;
        max-height: 8;
    }

    # slash command completion menu
    #completion {
        height: auto;
        max-height: 10;
        padding: 0 1;
        color: $text;
        background: $boost;
    }

    #status-bar {
        height: 1;
        padding: 0 1;
        background: $boost;
        color: $text;
        text-style: bold;
    }
    """

    def __init__(
        self,
        providers: list[ProviderConfig],
        config: Config,
        registry: Registry | None = None,
        engine: Engine | None = None,
        mcp_server_count: int = 0,
        mcp_tool_count: int = 0,
        runtime: SessionRuntime | None = None,
        writer: Writer | None = None,
        memory_manager: MemoryManager | None = None,
        instruction_text: str = "",
        memory_text: str = "",
        sessions_dir: str = "",
        catalog: Catalog | None = None,
        skill_executor: Executor | None = None,
        hook_engine: object | None = None,
        task_manager: TaskManager | None = None,
        agent_tool: AgentTool | None = None,
        worktree_mgr: worktree.Manager | None = None,
        team_manager=None,
        coordinator_mode: bool = False,
    ) -> None:
        super().__init__()
        self._providers = providers
        self._config = config
        self._tool_registry = registry or new_default_registry()
        self._engine = engine
        self._mcp_server_count = mcp_server_count
        self._mcp_tool_count = mcp_tool_count
        self._selected_provider: ProviderConfig | None = None
        self._provider: Provider | None = None
        self._agent: Agent | None = None
        self._runtime = runtime or SessionRuntime(
            replacement=ContentReplacementState(),
            recovery=RecoveryState(),
            auto_tracking=AutoCompactTrackingState(),
            session=new_session_context(str(Path.cwd())),
        )
        self._writer = writer
        self._memory_manager = memory_manager
        if self._memory_manager is not None:
            self._memory_manager.set_on_updated(self._on_memory_updated)
        self._instruction_text = instruction_text
        self._memory_text = memory_text
        self._sessions_dir = sessions_dir or str(Path.cwd() / ".cowcode" / "sessions")
        self._catalog = catalog or Catalog()
        self._skill_executor = skill_executor
        self.hook_engine = hook_engine
        self.task_manager = task_manager or TaskManager()
        self._agent_tool = agent_tool
        self.worktree_mgr = worktree_mgr
        self.team_manager = team_manager
        self.coordinator_mode = coordinator_mode
        self.active_cwd = ""
        if self.worktree_mgr is not None:
            session = self.worktree_mgr.current_session()
            if session is not None:
                self.active_cwd = session.worktree_path
        self._runtime.hook_engine = hook_engine
        self._session: Session | None = None
        self._full_response = ""
        self._timer_handle: Timer | None = None
        self._timer_start = 0.0
        self._is_streaming = False
        self._conversation: RichLog
        self._input: MessageInput
        self._timer_label: Static
        self._status_bar: Static
        self._context_header: ContextHeader
        self._streaming_response: Static
        self._resume_state: ResumeState | None = None
        self._cmd_registry = CommandRegistry()
        register_builtins(self._cmd_registry)
        if self._skill_executor is not None:
            self._refresh_skill_commands()
        self._completion = CompletionMenu()
        self._completion_view: Static
        self._pending_println: list[tuple[str, str]] = []

        # 权限模式与待批准状态
        self._mode: Mode = engine.start_mode if engine else Mode.DEFAULT
        self._iter: int = 0
        self._usage_in: int = 0
        self._usage_out: int = 0
        self._cur_tools: list[ToolDisplay] = []
        self._turn_cancel: asyncio.Event | None = None
        self._pending_approval: ApprovalRequest | None = None
        self._approve_cursor: int = 0

        # 交互式澄清状态
        self._pending_question: AskUserEvent | None = None
        self._ask_user_mode: Mode = Mode.DEFAULT

    def compose(self) -> ComposeResult:
        yield Static(CAT_BANNER, id="banner")
        yield ContextHeader()
        yield RichLog(id="conversation", wrap=True, markup=True)
        yield Static("", id="streaming-response")
        yield Static("", id="timer")
        yield MessageInput(
            placeholder="Type your message... (Enter to send, Alt+Enter for newline)",
            id="input-box",
            show_line_numbers=False,
            soft_wrap=True,
        )
        yield Static("", id="completion")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._conversation = self.query_one("#conversation", RichLog)
        self._input = self.query_one("#input-box", MessageInput)
        self._timer_label = self.query_one("#timer", Static)
        self._completion_view = self.query_one("#completion", Static)
        self._status_bar = self.query_one("#status-bar", Static)
        self._context_header = self.query_one(ContextHeader)
        self._streaming_response = self.query_one("#streaming-response", Static)

        self._conversation.write(Text(f"cwd: {Path.cwd()}", style="dim"))
        self._conversation.write(
            Text(
                _format_mcp_status(
                    self._mcp_server_count,
                    self._mcp_tool_count,
                ),
                style="green",
            )
        )
        self._conversation.write(Text("Ready. Send a message to begin.", style="green"))
        self.run_worker(self._dispatch_session_start())
        self.run_worker(consume_task_done(self))

        if len(self._providers) == 1:
            self._select_provider(self._providers[0])
        else:
            self.push_screen(
                ProviderSelectScreen(self._providers),
                callback=self._on_provider_selected,
            )

    async def _dispatch_session_start(self) -> None:
        await self._dispatch_hook(HookEvent.SESSION_START)

    async def _dispatch_session_end(self) -> None:
        await self._dispatch_hook(HookEvent.SESSION_END)

    async def _dispatch_hook(self, event: HookEvent, **extra: object) -> None:
        engine = self.hook_engine
        if engine is None:
            return
        payload = {
            "event": event.value,
            "session_id": self._runtime.session.session_id,
            "cwd": str(Path.cwd()),
            "mode": str(self._mode),
        }
        payload.update(extra)
        result = await engine.dispatch(event, payload)
        await self._runtime.append_reminders(result.injected_prompts)

    def on_key(self, event) -> None:
        """Resume 模式与 slash 补全模式下截获导航按键。"""

        state = self._resume_state
        if (
            state is None
            and self._completion.active
            and self._handle_completion_key(event)
        ):
            return
        if state is None:
            return
        key = getattr(event, "key", "")
        char = getattr(event, "character", None)
        handled = True
        if key == "up":
            if state.filtered:
                state.selected = max(0, state.selected - 1)
        elif key == "down":
            if state.filtered:
                state.selected = min(len(state.filtered) - 1, state.selected + 1)
        elif key == "backspace":
            state.query = state.query[:-1]
            self._filter_resume_items()
        elif key == "escape":
            self._exit_resume_mode()
        elif isinstance(char, str) and char and char.isprintable():
            state.query += char
            self._filter_resume_items()
        else:
            handled = False
        if handled:
            self._input.clear()
            if self._resume_state is not None:
                self._render_resume_list()
            self._sync_completion_from_input()
            event.stop()

    def action_toggle_context(self) -> None:
        self._context_header.toggle_context()

    def action_cancel_or_quit(self) -> None:
        """Esc/Ctrl+C：流式态/待批准态取消本轮；空闲态退出。"""
        if self._resume_state is not None:
            self._exit_resume_mode()
        elif self._is_streaming and self._turn_cancel is not None:
            self._turn_cancel.set()
        elif self._pending_approval is not None:
            # 待批准态取消：兜底送 DENY_ONCE 解阻塞
            if not self._pending_approval.respond.done():
                self._pending_approval.respond.set_result(Outcome.DENY_ONCE)
            self._pending_approval = None
        else:
            self.exit()

    def action_cycle_mode(self) -> None:
        """F2：循环切换权限模式。"""
        if self._resume_state is not None:
            return
        from cowcode.permission import next_mode

        self._mode = next_mode(self._mode)
        mode_names = {
            Mode.DEFAULT: "DEFAULT",
            Mode.ACCEPT_EDITS: "ACCEPT EDITS",
            Mode.PLAN: "PLAN",
            Mode.BYPASS: "BYPASS",
        }
        self._conversation.write("")
        self._conversation.write(
            Text(
                f"已切换到 {mode_names.get(self._mode, str(self._mode))} 模式",
                style="italic",
            )
        )
        self._update_status_bar()

    def _select_provider(self, provider_config: ProviderConfig) -> None:
        self._selected_provider = provider_config
        if self._writer is not None:
            self._writer.bind_model(provider_config.model)
        self._session = Session(
            on_append=self._writer.on_append if self._writer is not None else None,
            on_replace=self._writer.on_replace if self._writer is not None else None,
        )
        self._provider = create_provider(provider_config)
        if self._skill_executor is not None:
            self._skill_executor.provider_factory = self._create_selected_provider
        if self._memory_manager is not None:
            self._memory_manager.set_provider(self._provider, provider_config.model)
        self._runtime.context_window = effective_context_window(provider_config)
        self._agent = None
        self._mode = self._engine.start_mode if self._engine else Mode.DEFAULT
        self._update_status_bar()
        self._input.focus()

    def _create_selected_provider(self, model: str | None = None) -> Provider | None:
        if self._selected_provider is None:
            return None
        provider_config = self._selected_provider
        if model:
            provider_config = replace(provider_config, model=model)
        return create_provider(provider_config)

    def _on_provider_selected(self, provider_index: str | None) -> None:
        if provider_index is None:
            return
        self._select_provider(self._providers[int(provider_index)])

    def _on_memory_updated(
        self, memory_text: str, changed_files: list[str] | None = None
    ) -> None:
        self._memory_text = memory_text
        self._agent = None
        if changed_files:
            self._print_notice("已更新记忆：" + ", ".join(changed_files))

    def hook_sources(self) -> list[str]:
        engine = self.hook_engine
        return [] if engine is None else engine.sources

    def hook_rules(self) -> list[HookRule]:
        engine = self.hook_engine
        return [] if engine is None else engine.rules

    def _ensure_agent(self) -> Agent | None:
        if self._provider is None:
            return None
        environment = gather_environment(
            version=__version__, model=self._selected_provider.model
        ).render()
        if self._agent is None or self._environment_changed(environment):
            self._agent = Agent(
                self._provider,
                self._tool_registry,
                system_prompt=build_system_prompt(
                    self._config.system_prompt,
                    self._instruction_text,
                    self._memory_text,
                    self._render_skills_catalog_prompt(),
                ),
                environment=environment,
                engine=self._engine,
                runtime=self._runtime,
                memory_manager=self._memory_manager,
                hook_engine=self.hook_engine,
            )
            if self.coordinator_mode:
                self._agent.set_allowed_tools(coordinator.allowed_tools())
                self._agent.append_system_prompt(coordinator.system_prompt_suffix())
            if self._agent_tool is not None:
                # AgentTool 通过 getter 拿 parent；这里保留触发点，便于未来显式回填。
                pass
        return self._agent

    def _environment_changed(self, environment: str) -> bool:
        agent = self._agent
        return agent is None or getattr(agent, "_environment", "") != environment

    def _render_skills_catalog_prompt(self) -> str:
        items = [
            SkillCatalogItem(skill.meta.name, skill.meta.description)
            for skill in self._catalog.list()
        ]
        return render_skills_catalog(items)

    def _update_status_bar(self) -> None:
        if self._selected_provider is None:
            return
        mode_colors = {
            Mode.DEFAULT: "green",
            Mode.ACCEPT_EDITS: "yellow",
            Mode.PLAN: "bold yellow",
            Mode.BYPASS: "red",
        }
        mode_labels = {
            Mode.DEFAULT: "DEFAULT",
            Mode.ACCEPT_EDITS: "ACCEPT EDITS",
            Mode.PLAN: "PLAN",
            Mode.BYPASS: "BYPASS",
        }
        color = mode_colors.get(self._mode, "")
        label = mode_labels.get(self._mode, str(self._mode))
        parts = [f"[{color}]{label}[/]"]
        parts.append("|")
        parts.append(self._selected_provider.model)
        if self.coordinator_mode:
            parts.append("[bold magenta][COORDINATOR][/]")
        if self._usage_in or self._usage_out:
            parts.append(
                f"↑{_compact_tok(self._usage_in)} ↓{_compact_tok(self._usage_out)} tok"
            )
        self._status_bar.update(Text.from_markup("  ".join(parts)))

    def _start_timer(self) -> None:
        self._timer_start = time.time()
        self._update_timer_display()
        if self._timer_handle is not None:
            self._timer_handle.stop()
        self._timer_handle = self.set_interval(0.2, self._update_timer_display)

    def _update_timer_display(self) -> None:
        elapsed = time.time() - self._timer_start
        parts = []
        if self._cur_tools:
            parts.append(
                "\n".join(f"● {td.name}({td.args}) Running…" for td in self._cur_tools)
            )
        else:
            status = f"Imagining… ({elapsed:.1f}s"
            if self._iter > 0:
                status += f" · 第 {self._iter} 轮"
            status += ")"
            parts.append(status)
        self._timer_label.update("\n".join(parts))

    def _stop_timer(self) -> None:
        elapsed = time.time() - self._timer_start
        if self._timer_handle is not None:
            self._timer_handle.stop()
            self._timer_handle = None
        self._timer_label.update(f"Done in {elapsed:.1f}s")

    def _print_user(self, text: str) -> None:
        self._conversation.write("")
        self._conversation.write(Text("You:", style="bold blue"))
        self._conversation.write(Text(text, style="blue"))

    def _print_error(self, text: str) -> None:
        self._conversation.write("")
        self._conversation.write(Text(f"Error: {text}", style="bold red"))

    def _print_notice(self, text: str) -> None:
        self._conversation.write("")
        self._conversation.write(Text(text, style="dim italic"))

    def _refresh_skill_commands(self) -> None:
        if self._skill_executor is None:
            return
        remove_skill_commands(self._cmd_registry)
        register_skills_as_commands(
            self._cmd_registry,
            self.list_catalog_skills(),
            self._skill_executor,
        )

    def _render_completion(self) -> None:
        if hasattr(self, "_completion_view"):
            self._completion_view.update(
                self._completion.render(self.size.width)
                if self._completion.active
                else ""
            )

    def _sync_completion_from_input(self) -> None:
        if not hasattr(self, "_input"):
            return
        self._refresh_skill_commands()
        self._completion.update(self._input.text, self._cmd_registry)
        self._render_completion()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if getattr(event.text_area, "id", "") == "input-box":
            self._sync_completion_from_input()

    def _handle_completion_key(self, event) -> bool:
        key = getattr(event, "key", "")
        if key == "up":
            self._completion.move_up()
        elif key == "down":
            self._completion.move_down()
        elif key == "escape":
            self._completion.hide()
        elif key in {"enter", "tab"}:
            selected = self._completion.selected()
            self._completion.hide()
            if selected is not None:
                self._input.text = f"/{selected.name}"
                self.run_worker(self._handle_send(), exclusive=True)
        else:
            return False
        self._render_completion()
        event.stop()
        return True

    def _set_streaming_response(self, text: str) -> None:
        if text:
            self._streaming_response.update(Text(f"Cowcode:\n{text}", style="yellow"))
        else:
            self._streaming_response.update("")

    def _print_tool_start(self, name: str, args: str) -> None:
        self._conversation.write("")
        self._conversation.write(Text(f"* {name}({args})", style="bold cyan"))

    def _print_tool_result(self, result: str, is_error: bool) -> None:
        style = "red" if is_error else "dim"
        summary = truncate_text(result, max_lines=8, max_chars=1200)
        self._conversation.write(
            Text("  -> " + summary.replace("\n", "\n     "), style=style)
        )

    def println(self, msg: str) -> None:
        self._pending_println.append(("notice", msg))

    def error(self, msg: str) -> None:
        self._pending_println.append(("error", msg))

    def mode(self) -> Mode:
        return self._mode

    def set_mode(self, mode: Mode) -> None:
        self._mode = mode
        self._update_status_bar()

    def inject_and_send(self, display_label: str, preset_prompt: str) -> None:
        if self._session is None:
            self.error("Not connected to a provider.")
            return
        self._session.append("user", preset_prompt)
        self._print_notice(f"已注入 {display_label}。")
        self._start_agent_run(self._mode)

    def list_catalog_skills(self) -> list[SkillSummary]:
        return [
            SkillSummary(
                name=skill.meta.name,
                description=skill.meta.description,
                source=str(skill.source),
                mode=skill.meta.mode,
            )
            for skill in self._catalog.list()
        ]

    def list_active_skills(self) -> list[str]:
        return self._runtime.active_skills.names()

    def clear_active_skills(self) -> None:
        self._runtime.active_skills.clear()

    async def append_assistant_message(self, text: str) -> None:
        if self._session is None:
            self.error("Not connected to a provider.")
            return
        self._session.append("assistant", text)
        self._conversation.write("")
        self._conversation.write(Text("Cowcode:", style="bold yellow"))
        self._conversation.write(Markdown(text))

    def recent_messages(self, n: int) -> list[Message]:
        if self._session is None:
            return []
        return self._session.get_history()[-n:]

    def all_messages(self) -> list[Message]:
        if self._session is None:
            return []
        return self._session.get_history()

    def usage_in(self) -> int:
        return self._usage_in

    def usage_out(self) -> int:
        return self._usage_out

    def model_name(self) -> str:
        return (
            self._selected_provider.model if self._selected_provider is not None else ""
        )

    def cwd(self) -> str:
        return self.active_cwd or str(Path.cwd())

    def worktree_accessor(self) -> WorktreeAccessor | None:
        if self.worktree_mgr is None:
            return None
        return WorktreeAdapter(self.worktree_mgr, self._set_active_cwd)

    def _set_active_cwd(self, cwd: str) -> None:
        self.active_cwd = cwd

    def _effective_cwd(self) -> str:
        return self.active_cwd or str(Path.cwd())

    def tool_count(self) -> int:
        return self._tool_registry.count()

    def memory_files(self) -> list[str]:
        if self._memory_manager is None:
            return []
        project, user = self._memory_manager.list_files()
        return project + user

    def session_path(self) -> str:
        return str(self._writer.path) if self._writer is not None else ""

    def session_id(self) -> str:
        return self._runtime.session.session_id if self._runtime is not None else ""

    def idle(self) -> bool:
        return (
            not self._is_streaming
            and self._pending_approval is None
            and self._resume_state is None
        )

    def quit(self) -> None:
        if self._turn_cancel is not None:
            self._turn_cancel.set()
        self.exit()

    def force_compact(self) -> None:
        self.run_worker(self._handle_compact_command(), exclusive=True)

    def open_resume_menu(self) -> None:
        sessions = list_sessions(self._sessions_dir)
        if not sessions:
            self._print_notice("没有可恢复的会话。")
            return
        self._enter_resume_mode(sessions)

    async def clear_and_new_session(self) -> None:
        try:
            new_context = new_session_context(str(Path.cwd()))
            new_writer = Writer(new_context.session_dir)
            if self._selected_provider is not None:
                new_writer.bind_model(self._selected_provider.model)
        except Exception as exc:
            self.error(str(exc))
            return
        await self._dispatch_session_end()
        old_writer = self._writer
        self._writer = new_writer
        self._session = Session(
            on_append=new_writer.on_append, on_replace=new_writer.on_replace
        )
        await self._runtime.reset_for_new_session(new_context)
        self._agent = None
        self._iter = 0
        self._usage_in = 0
        self._usage_out = 0
        if old_writer is not None:
            old_writer.close()
        self._conversation.clear()
        self._context_header.clear_context()
        self._set_streaming_response("")
        self._update_status_bar()
        await self._dispatch_session_start()

    def _parse_skill_invocation(self, text: str) -> tuple[str, str] | None:
        raw = text.strip()
        if not raw.startswith("/"):
            return None
        tail = raw[1:].strip()
        if not tail or tail.startswith("/"):
            return None
        name, _, args = tail.partition(" ")
        name = name.lower()
        if self._catalog.get(name) is None:
            return None
        return name, args.strip()

    async def dispatch_slash(self, text: str) -> bool:
        """本地分发 slash 命令。"""

        name, is_slash = parse(text)
        if not is_slash:
            return False
        self._refresh_skill_commands()
        self._pending_println.clear()
        raw_tail = text.strip()[1:].strip()
        raw_name, _, raw_args = raw_tail.partition(" ")
        cmd = self._cmd_registry.lookup(name)
        if cmd is None and raw_args.strip():
            candidate = self._cmd_registry.lookup(raw_name.lower())
            if candidate is not None and candidate.args_handler is not None:
                name = raw_name.lower()
                cmd = candidate
        skill_invocation = self._parse_skill_invocation(text)
        if skill_invocation is not None and (cmd is None or cmd.is_skill):
            skill_name, skill_args = skill_invocation
            if not self.idle():
                self.error("请等待当前任务完成")
            elif self._skill_executor is not None:
                await self._skill_executor.execute(self, skill_name, skill_args)
            else:
                self.error(f"skill executor not ready: {skill_name}")
        elif cmd is None:
            self.println("未知命令：输入 /help 查看可用命令")
        elif cmd.kind in {Kind.UI, Kind.PROMPT} and not self.idle():
            self.error("请等待当前任务完成")
        else:
            try:
                if cmd.args_handler is not None:
                    _, _, command_args = text.strip()[1:].partition(" ")
                    await cmd.args_handler(self, command_args.strip())
                else:
                    await cmd.handler(self)
            except Exception as exc:
                self.error(str(exc))
        for kind, msg in self._pending_println:
            if kind == "error":
                self._print_error(msg)
            else:
                self._print_notice(msg)
        self._pending_println.clear()
        self._input.clear()
        self._completion.hide()
        self._render_completion()
        return True

    async def _handle_resume_command(self) -> None:
        if self._is_streaming:
            self._print_notice("请等待当前任务完成。")
            return
        sessions = list_sessions(self._sessions_dir)
        if not sessions:
            self._print_notice("没有可恢复的会话。")
            return
        self._enter_resume_mode(sessions)

    def _enter_resume_mode(self, sessions: list[SessionInfo]) -> None:
        self._resume_state = ResumeState(items=sessions, filtered=list(sessions))
        self._input.clear()
        self._set_streaming_response("")
        self._input.placeholder = (
            "Search sessions... (↑/↓ select, Enter resume, Esc cancel)"
        )
        self._render_resume_list()
        self._input.focus()

    def _exit_resume_mode(self) -> None:
        self._resume_state = None
        self._input.clear()
        self._input.placeholder = (
            "Type your message... (Enter to send, Alt+Enter for newline)"
        )
        self._set_streaming_response("")
        self._print_notice("已取消恢复会话。")
        self._input.focus()

    def _filter_resume_items(self) -> None:
        state = self._resume_state
        if state is None:
            return
        query = state.query.strip().lower()
        if not query:
            state.filtered = list(state.items)
        else:
            state.filtered = [
                item
                for item in state.items
                if query in item.title.lower()
                or query in item.model.lower()
                or query in item.id.lower()
            ]
        if not state.filtered:
            state.selected = 0
        else:
            state.selected = min(state.selected, len(state.filtered) - 1)

    def _render_resume_list(self) -> None:
        state = self._resume_state
        if state is None:
            return
        lines = [
            "Resume sessions",
            f"Search: {state.query or '(empty)'}  ·  ↑/↓ select  Enter resume  Esc cancel",
        ]
        if not state.filtered:
            lines.append("No matching sessions.")
        else:
            for index, info in enumerate(state.filtered[:20]):
                marker = "▶ " if index == state.selected else "  "
                lines.append(marker + _format_session_item(info))
            if len(state.filtered) > 20:
                lines.append(f"... {len(state.filtered) - 20} more")
        self._set_streaming_response("\n".join(lines))

    async def _resume_selected_session(self) -> None:
        state = self._resume_state
        if state is None or not state.filtered:
            return
        info = state.filtered[state.selected]
        await self._do_resume_session(info)

    async def _do_resume_session(self, info: SessionInfo) -> None:
        try:
            msgs = load_session(info.dir)
            new_writer = Writer.open_existing(info.dir)
            if self._selected_provider is not None:
                new_writer.bind_model(self._selected_provider.model)
            new_session = Session.from_messages(
                msgs,
                on_append=new_writer.on_append,
                on_replace=new_writer.on_replace,
            )
            try:
                new_context = open_session_context(str(Path.cwd()), info.id)
            except Exception:
                new_writer.close()
                raise
        except Exception as exc:
            self._print_error(f"恢复会话失败: {exc}")
            return

        old_writer = self._writer
        self._writer = new_writer
        self._session = new_session
        self._runtime.session = new_context
        self._runtime.usage_anchor = 0
        self._runtime.anchor_msg_len = 0
        self._agent = None
        if old_writer is not None:
            old_writer.close()

        self._resume_state = None
        self._input.clear()
        self._input.placeholder = (
            "Type your message... (Enter to send, Alt+Enter for newline)"
        )
        self._set_streaming_response("")
        self._print_notice(f"已恢复会话 {info.id}，共 {len(msgs)} 条消息")
        self._append_resume_gap_notice_if_needed(info)
        await self._compact_restored_session_if_needed()
        self._input.focus()

    async def _compact_restored_session_if_needed(self) -> None:
        if self._session is None or self._provider is None:
            return
        estimated = estimate_tokens(0, self._session.get_history(), 0)
        threshold = self._runtime.context_window - SUMMARY_RESERVE - AUTO_SAFETY_MARGIN
        if estimated < threshold:
            return
        agent = self._ensure_agent()
        if agent is None:
            return
        self._agent = agent
        defs = (
            self._tool_registry.read_only_definitions()
            if self._mode == Mode.PLAN
            else self._tool_registry.definitions()
        )
        self._print_notice(
            format_compact_notice(CompactEvent(CompactPhase.BEFORE_AUTO))
        )
        try:
            before, after = await agent.run_force_compact(self._session, defs)
        except Exception as exc:
            self._print_notice(
                format_compact_notice(CompactEvent(CompactPhase.AFTER_AUTO, err=exc))
            )
            return
        self._print_notice(
            format_compact_notice(
                CompactEvent(CompactPhase.AFTER_AUTO, before=before, after=after)
            )
        )

    def _append_resume_gap_notice_if_needed(self, info: SessionInfo) -> None:
        if self._session is None:
            return
        ts = last_message_ts(info.dir)
        if ts is None:
            return
        elapsed = int(time.time()) - ts
        if elapsed <= 6 * 60 * 60:
            return
        hours = max(1, elapsed // 3600)
        reminder = (
            f"[系统提示] 本会话已暂停约 {hours} 小时。"
            "部分上下文可能已过时，如需最新信息请重新读取相关文件。"
        )
        self._session.append("user", reminder)
        self._print_notice(reminder)

    async def _handle_compact_command(self) -> None:
        if self._session is None or self._provider is None:
            self._print_error("Not connected to a provider.")
            return
        agent = self._ensure_agent()
        if agent is None:
            self._print_error("Not connected to a provider.")
            return
        defs = (
            self._tool_registry.read_only_definitions()
            if self._mode == Mode.PLAN
            else self._tool_registry.definitions()
        )
        self._print_notice(
            format_compact_notice(CompactEvent(CompactPhase.BEFORE_AUTO))
        )
        self._timer_label.update("⟳ Compacting conversation...")
        self.refresh(layout=True)
        try:
            before, after = await agent.run_force_compact(self._session, defs)
        except Exception as exc:
            self._print_notice(
                format_compact_notice(CompactEvent(CompactPhase.AFTER_AUTO, err=exc))
            )
            self._timer_label.update("Compact failed")
            return
        self._print_notice(
            format_compact_notice(
                CompactEvent(CompactPhase.AFTER_AUTO, before=before, after=after)
            )
        )
        self._timer_label.update("Compact done")

    async def _handle_send(self) -> None:
        """提交当前输入，并消费 Agent 事件流。"""
        if self._is_streaming:
            return

        user_text = self._input.text.strip()
        if self._resume_state is not None:
            await self._resume_selected_session()
            return
        if not user_text:
            return

        # ----- 交互式澄清回答 -----
        if self._pending_question is not None:
            pending = self._pending_question
            self._pending_question = None
            self._input.clear()
            self._print_user(user_text)
            self._session.append(
                "user",
                f"Answer to: {pending.question}\n\n{user_text}",
            )
            self._print_notice("继续…")
            # 以澄清前的 mode 继续运行
            self._start_agent_run(self._ask_user_mode)
            return

        if user_text.lower() in {"quit", "exit"}:
            self.exit()
            return

        if await self.dispatch_slash(user_text):
            return

        if self._session is None or self._provider is None:
            self._print_error("Not connected to a provider.")
            return

        hook_result = await self._dispatch_user_prompt_submit(user_text)
        if hook_result is not None and hook_result.blocked:
            self._print_error(
                f"[hook {hook_result.blocking_hook_name}] {hook_result.reason}"
            )
            return

        self._input.clear()
        self._context_header.set_context(user_text)
        self._print_user(user_text)
        self._session.append("user", user_text)
        self._start_agent_run(self._mode)

    async def _dispatch_user_prompt_submit(self, text: str):
        engine = self.hook_engine
        if engine is None:
            return None
        payload = {
            "event": HookEvent.USER_PROMPT_SUBMIT.value,
            "session_id": self._runtime.session.session_id,
            "cwd": str(Path.cwd()),
            "mode": str(self._mode),
            "prompt": text,
        }
        result = await engine.dispatch(HookEvent.USER_PROMPT_SUBMIT, payload)
        await self._runtime.append_reminders(result.injected_prompts)
        return result

    def _on_user_answer(self, answer: str | None) -> None:
        """澄清弹窗回调——收到用户选择或自定义输入。"""
        if answer is None or self._pending_question is None:
            self._pending_question = None
            return
        pending = self._pending_question
        self._pending_question = None

        self._print_user(answer)
        self._session.append(
            "user",
            f"Answer to: {pending.question}\n\n{answer}",
        )
        self._print_notice("继续…")
        self._start_agent_run(self._ask_user_mode)

    def _on_approval_answer(self, answer: str | None) -> None:
        """权限审批弹窗回调——把用户选择转成 Outcome 并恢复 Agent。"""
        if answer is None or self._pending_approval is None:
            if (
                self._pending_approval is not None
                and not self._pending_approval.respond.done()
            ):
                self._pending_approval.respond.set_result(Outcome.DENY_ONCE)
            self._pending_approval = None
            return
        pending = self._pending_approval
        self._pending_approval = None
        # answer 格式为 "1. 允许本次" 等 —— 按序号判定
        if answer.startswith("2"):
            outcome = Outcome.ALLOW_FOREVER
        elif answer.startswith("3"):
            outcome = Outcome.DENY_ONCE
        else:
            outcome = Outcome.ALLOW_ONCE
        if not pending.respond.done():
            pending.respond.set_result(outcome)

    def _start_agent_run(self, mode: Mode) -> None:
        """启动 Agent Loop 并消费事件流。"""
        if self._session is None or self._provider is None:
            self._print_error("Not connected to a provider.")
            return
        if self._resume_state is not None:
            return

        self._full_response = ""
        self._set_streaming_response("")
        self._start_timer()
        self._turn_cancel = asyncio.Event()
        self._is_streaming = True
        self._iter = 0

        agent = self._ensure_agent()
        if agent is None:
            self._print_error("Not connected to a provider.")
            return
        self._agent = agent
        self.run_worker(self._consume_agent_events(agent, mode), exclusive=True)

    async def _consume_agent_events(self, agent: Agent, mode: Mode) -> None:
        """消费 Agent 事件流——由 Textual worker 驱动。"""
        try:
            with with_cwd(self._effective_cwd()):
                async for event in agent.run(
                    self._session, mode, self._turn_cancel, mode_getter=lambda: self._mode
                ):
                    if event.err is not None:
                        self._print_error(str(event.err))
                        break
                    if event.compact is not None:
                        self._print_notice(format_compact_notice(event.compact))
                        continue
                    if event.text:
                        self._full_response += event.text
                        self._set_streaming_response(self._full_response)
                    if event.tool is not None:
                        # 首个工具前先提交 preamble
                        if self._full_response and event.tool.phase == Phase.START:
                            # 只在没多个工具追加时才提交（提交只在第一次工具出现时做）
                            pass
                        if event.tool.phase == Phase.START:
                            if self._full_response:
                                self._conversation.write("")
                                self._conversation.write(
                                    Text("Cowcode:", style="bold yellow")
                                )
                                self._conversation.write(Markdown(self._full_response))
                                self._full_response = ""
                                self._set_streaming_response("")
                            self._cur_tools.append(
                                ToolDisplay(event.tool.name, event.tool.args)
                            )
                            self._print_tool_start(event.tool.name, event.tool.args)
                            self._update_timer_display()
                        else:
                            # PHASE_END：FIFO 弹出队首
                            if self._cur_tools:
                                self._cur_tools.pop(0)
                            self._print_tool_result(event.tool.result, event.tool.is_error)
                            self._update_timer_display()
                    if event.usage is not None:
                        self._usage_in += event.usage.input_tokens
                        self._usage_out += event.usage.output_tokens
                        self._update_status_bar()
                    if event.iter > 0:
                        self._iter = event.iter
                        self._update_timer_display()
                    if event.notice:
                        self._print_notice(event.notice)
                    if event.done:
                        break
                    if event.approval is not None:
                        # 权限 Ask——人在回路审批弹窗
                        self._pending_approval = event.approval
                        self._approve_cursor = 0
                        self._ask_user_mode = mode
                        options = [
                            "1. 允许本次",
                            "2. 永久允许（写入本地配置）",
                            "3. 拒绝本次",
                        ]
                        self.push_screen(
                            AskUserQuestionScreen(
                                f"{event.approval.name}({event.approval.args})\n{event.approval.reason}",
                                options,
                            ),
                            callback=self._on_approval_answer,
                        )
                    if event.ask_user is not None:
                        # 弹窗让用户选择或自定义输入
                        self._pending_question = event.ask_user
                        self._ask_user_mode = mode
                        if event.ask_user.options:
                            self.push_screen(
                                AskUserQuestionScreen(
                                    event.ask_user.question, event.ask_user.options
                                ),
                                callback=self._on_user_answer,
                            )
                        else:
                            self._conversation.write("")
                            self._conversation.write(Text("Cowcode:", style="bold yellow"))
                            self._conversation.write(
                                Markdown(f"**❓ {event.ask_user.question}**")
                            )
                            self._conversation.write(
                                Text(
                                    "\n请在输入框中回答后按 Enter 继续…",
                                    style="italic",
                                )
                            )
                            self._input.focus()
                        break
        finally:
            self._is_streaming = False
            self._stop_timer()
            self._context_header.clear_context()
            self._cur_tools.clear()
            self._iter = 0
            self._turn_cancel = None

        if self._full_response:
            self._set_streaming_response("")
            self._conversation.write("")
            self._conversation.write(Text("Cowcode:", style="bold yellow"))
            self._conversation.write(Markdown(self._full_response))


async def _amain() -> int:
    """异步装配 Cowcode 与 MCP 生命周期。"""
    if "--team-member" in sys.argv[1:]:
        from cowcode.team_member import parse_team_member_args, run_team_member

        return await run_team_member(parse_team_member_args(sys.argv[1:]))
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print("Cowcode - terminal AI coding assistant\n\nUsage: cowcode [--help]")
        return 0
    try:
        config, providers = load_configs()
    except FileNotFoundError:
        print("Error: Config file not found: config.yaml. Create config.yaml.")
        return 1
    except ConfigError as exc:
        print(f"Error: Invalid config: {exc}")
        return 1

    root = str(resolve_config_path().parent.resolve())
    instruction_text = InstructionsLoader(root).load()
    mem_mgr = MemoryManager(
        project_dir=str(Path(root) / ".cowcode" / "memory"),
        user_dir=str(Path.home() / ".cowcode" / "memory"),
        provider=None,
        model="",
    )
    memory_text = mem_mgr.load_index()
    session_context = new_session_context(root)
    writer = Writer(session_context.session_dir)
    sessions_dir = str(Path(root) / ".cowcode" / "sessions")
    asyncio.create_task(
        asyncio.to_thread(clean_expired, sessions_dir, timedelta(days=30))
    )
    engine, err = new_engine(root)
    if err is not None:
        print("权限引擎降级:", err, file=sys.stderr)

    registry = new_default_registry()
    mcp_config = mcp_client.load_config(root)
    manager = await mcp_client.new_manager(mcp_config, version=__version__)
    try:
        for remote_tool in manager.tools():
            registry.register(remote_tool)

        catalog = Catalog.load(Path(root))
        subagent_catalog = load_subagent_catalog(root)
        from cowcode.team import Manager as TeamManager
        from cowcode.team.registry import AgentNameRegistry

        name_reg = AgentNameRegistry()
        task_manager = TaskManager()
        task_manager.set_name_registry(name_reg)
        registry.register(BgTaskListTool(task_manager))
        registry.register(BgTaskGetTool(task_manager))
        registry.register(TaskStopTool(task_manager))
        hook_engine = hook.load(root)
        runtime = SessionRuntime(
            replacement=ContentReplacementState(),
            recovery=RecoveryState(),
            auto_tracking=AutoCompactTrackingState(),
            session=session_context,
            hook_engine=hook_engine,
        )
        active = runtime.active_skills
        registry.register(LoadSkillTool(catalog, active, registry))
        registry.register(InstallSkillTool(catalog, Path(root)))
        for issue in catalog.validate_tools(registry):
            print(
                f'skill {issue.skill_name}: allowed_tool "{issue.tool_name}" not registered, skipped',
                file=sys.stderr,
            )
            catalog.remove(issue.skill_name)

        def _provider_factory(model: str | None = None) -> Provider | None:
            selected = providers[0] if providers else None
            if selected is None:
                return None
            provider_config = selected
            if model:
                provider_config = ProviderConfig(
                    name=selected.name,
                    protocol=selected.protocol,
                    base_url=selected.base_url,
                    api_key=selected.api_key,
                    model=model,
                )
            return create_provider(provider_config)

        skill_executor = Executor(
            catalog=catalog,
            active=active,
            registry=registry,
            provider_factory=_provider_factory,
            runtime=runtime,
            engine=engine,
            memory_manager=mem_mgr,
        )
        try:
            worktree_mgr = worktree.Manager(root)
        except Exception as exc:
            print(f"Worktree 管理器降级: {exc}", file=sys.stderr)
            worktree_mgr = None
        else:
            asyncio.create_task(
                worktree_mgr.sweep_stale(datetime.now() - timedelta(hours=24))  # type: ignore[attr-defined]
            )

        from cowcode.team.tools import register_team_tools

        team_manager = TeamManager(Path.home(), root, worktree_mgr, task_manager, name_reg)
        team_manager.catalog = subagent_catalog
        team_manager.registry_tools = registry
        register_team_tools(registry, team_manager)
        task_manager.on_task_done(team_manager.handle_task_done)

        app_ref: dict[str, CowcodeApp] = {}
        agent_tool = AgentTool(
            subagent_catalog,
            task_manager,
            registry,
            parent_getter=lambda: app_ref["app"]._ensure_agent() if "app" in app_ref else None,
            messages_getter=lambda: app_ref["app"].all_messages() if "app" in app_ref else [],
            bg_enabled=config.effective_enable_subagent_background(),
            worktree_mgr=worktree_mgr,
            team_hook=team_manager,
        )
        registry.register(agent_tool)
        app = CowcodeApp(
            providers=providers,
            config=config,
            registry=registry,
            engine=engine,
            runtime=runtime,
            writer=writer,
            memory_manager=mem_mgr,
            instruction_text=instruction_text,
            memory_text=memory_text,
            sessions_dir=sessions_dir,
            catalog=catalog,
            skill_executor=skill_executor,
            hook_engine=hook_engine,
            task_manager=task_manager,
            agent_tool=agent_tool,
            worktree_mgr=worktree_mgr,
            team_manager=team_manager,
            coordinator_mode=coordinator.is_enabled(config),
        )
        app_ref["app"] = app
        await app.run_async()
        if hook_engine is not None:
            await hook_engine.dispatch(
                HookEvent.SESSION_END,
                {
                    "event": HookEvent.SESSION_END.value,
                    "session_id": runtime.session.session_id,
                    "cwd": root,
                    "mode": str(engine.start_mode),
                },
            )
    finally:
        writer.close()
        await manager.close()
    return 0


def main() -> None:
    """cowcode 命令入口。"""
    raise SystemExit(asyncio.run(_amain()))
