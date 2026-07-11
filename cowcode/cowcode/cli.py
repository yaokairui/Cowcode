"""Textual TUI for Cowcode."""

from __future__ import annotations

import asyncio
import time
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

from cowcode import __version__
from cowcode.agent import Agent, AskUserEvent, Mode, Phase
from cowcode.config import Config, ConfigError, ProviderConfig, load_configs
from cowcode.environment import gather_environment
from cowcode.prompt import EXECUTE_DIRECTIVE, build_system_prompt
from cowcode.provider import Provider, create_provider
from cowcode.session import Session
from cowcode.tool import Registry, new_default_registry, truncate_text

__all__ = ["CowcodeApp", "main"]

_CONTEXT_COLLAPSED_H = 4
_CONTEXT_EXPANDED_H = 12

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
    ) -> None:
        super().__init__()
        self._providers = providers
        self._config = config
        self._tool_registry = registry or new_default_registry()
        self._selected_provider: ProviderConfig | None = None
        self._provider: Provider | None = None
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

        # ch04 新增字段
        self._mode: Mode = Mode.NORMAL
        self._iter: int = 0
        self._usage_in: int = 0
        self._usage_out: int = 0
        self._cur_tools: list[ToolDisplay] = []
        self._turn_cancel: asyncio.Event | None = None

        # 交互式澄清状态
        self._pending_question: AskUserEvent | None = None
        self._ask_user_mode: Mode = Mode.NORMAL

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
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._conversation = self.query_one("#conversation", RichLog)
        self._input = self.query_one("#input-box", MessageInput)
        self._timer_label = self.query_one("#timer", Static)
        self._status_bar = self.query_one("#status-bar", Static)
        self._context_header = self.query_one(ContextHeader)
        self._streaming_response = self.query_one("#streaming-response", Static)

        self._conversation.write(Text(f"cwd: {Path.cwd()}", style="dim"))
        self._conversation.write(Text("Ready. Send a message to begin.", style="green"))

        if len(self._providers) == 1:
            self._select_provider(self._providers[0])
        else:
            self.push_screen(
                ProviderSelectScreen(self._providers),
                callback=self._on_provider_selected,
            )

    def action_toggle_context(self) -> None:
        self._context_header.toggle_context()

    def action_cancel_or_quit(self) -> None:
        """Esc/Ctrl+C：流式态取消本轮；空闲态退出。"""
        if self._is_streaming and self._turn_cancel is not None:
            self._turn_cancel.set()
        else:
            self.exit()

    def _select_provider(self, provider_config: ProviderConfig) -> None:
        self._selected_provider = provider_config
        self._session = Session()
        self._provider = create_provider(provider_config)
        self._mode = Mode.NORMAL
        self._update_status_bar()
        self._input.focus()

    def _on_provider_selected(self, provider_index: str | None) -> None:
        if provider_index is None:
            return
        self._select_provider(self._providers[int(provider_index)])

    def _update_status_bar(self) -> None:
        if self._selected_provider is None:
            return
        parts = [self._selected_provider.name]
        if self._mode == Mode.PLAN:
            parts.append("[bold yellow]PLAN[/]")
        parts.append("|")
        parts.append(self._selected_provider.model)
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

    async def _handle_send(self) -> None:
        """提交当前输入，并消费 Agent 事件流。"""
        if self._is_streaming:
            return

        user_text = self._input.text.strip()
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

        if user_text.lower() in {"quit", "exit", "/exit"}:
            self.exit()
            return

        if self._session is None or self._provider is None:
            self._print_error("Not connected to a provider.")
            return

        self._input.clear()

        # 处理 /plan 和 /do
        if user_text == "/plan":
            self._mode = Mode.PLAN
            self._print_notice(
                "已进入计划模式（只读工具），产出计划后请用 /do 批准执行。"
            )
            self._update_status_bar()
            return

        if user_text == "/do":
            self._mode = Mode.NORMAL
            self._session.append("user", EXECUTE_DIRECTIVE)
            self._print_notice("已切回正常模式，开始按计划执行。")
            self._update_status_bar()
            # 走启动流程
        else:
            # 普通文本
            self._context_header.set_context(user_text)
            self._print_user(user_text)
            self._session.append("user", user_text)

        self._start_agent_run(self._mode)

    def _start_agent_run(self, mode: Mode) -> None:
        """启动 Agent Loop 并消费事件流。"""
        if self._session is None or self._provider is None:
            self._print_error("Not connected to a provider.")
            return

        self._full_response = ""
        self._set_streaming_response("")
        self._start_timer()
        self._turn_cancel = asyncio.Event()
        self._is_streaming = True
        self._iter = 0

        environment = gather_environment(
            version=__version__, model=self._selected_provider.model
        ).render()
        agent = Agent(
            self._provider,
            self._tool_registry,
            system_prompt=build_system_prompt(self._config.system_prompt),
            environment=environment,
        )
        self.run_worker(self._consume_agent_events(agent, mode), exclusive=True)

    async def _consume_agent_events(self, agent: Agent, mode: Mode) -> None:
        """消费 Agent 事件流——由 Textual worker 驱动。"""
        try:
            async for event in agent.run(self._session, mode, self._turn_cancel):
                if event.err is not None:
                    self._print_error(str(event.err))
                    break
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
                if event.ask_user is not None:
                    # 暂停 Agent Loop 等待用户回答
                    self._pending_question = event.ask_user
                    self._ask_user_mode = mode
                    self._conversation.write("")
                    self._conversation.write(
                        Text("Cowcode:", style="bold yellow")
                    )
                    opts_md = ""
                    if event.ask_user.options:
                        opts_md = "\n".join(
                            f"- {opt}" for opt in event.ask_user.options
                        ) + "\n\n"
                    self._conversation.write(
                        Markdown(
                            f"**❓ {event.ask_user.question}**\n\n"
                            + opts_md
                        )
                    )
                    if event.ask_user.options:
                        self._conversation.write(
                            Text(
                                "请选择或输入回答后按 Enter 继续…",
                                style="italic",
                            )
                        )
                    else:
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


def main() -> None:
    """cowcode 命令入口。"""
    try:
        config, providers = load_configs()
    except FileNotFoundError:
        print("Error: Config file not found: config.yaml. Create config.yaml.")
        raise SystemExit(1)
    except ConfigError as exc:
        print(f"Error: Invalid config: {exc}")
        raise SystemExit(1)

    CowcodeApp(
        providers=providers,
        config=config,
        registry=new_default_registry(),
    ).run()
