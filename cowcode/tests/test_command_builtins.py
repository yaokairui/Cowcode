"""内置 slash 命令测试。"""

from __future__ import annotations

import pytest

from cowcode.command import NopUI, Registry, register_builtins
from cowcode.command.builtin_ui import handle_compact
from cowcode.command.builtin_prompt import handle_do
from cowcode.command.builtin_local import handle_status
from cowcode.permission import Mode


EXPECTED = {
    "clear",
    "compact",
    "do",
    "exit",
    "help",
    "hooks",
    "memory",
    "permission",
    "plan",
    "resume",
    "session",
    "skill",
    "status",
}


class RecordingUI(NopUI):
    def __init__(self, *, idle: bool = True) -> None:
        self.printed: list[str] = []
        self.errors: list[str] = []
        self.modes: list[Mode] = []
        self.injected: list[tuple[str, str]] = []
        self.compacted = False
        self._idle = idle

    def println(self, msg: str) -> None:
        self.printed.append(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def set_mode(self, mode: Mode) -> None:
        self.modes.append(mode)

    def inject_and_send(self, display_label: str, preset_prompt: str) -> None:
        self.injected.append((display_label, preset_prompt))

    def force_compact(self) -> None:
        self.compacted = True

    def idle(self) -> bool:
        return self._idle


def test_register_builtins_all_registered() -> None:
    reg = Registry()
    register_builtins(reg)
    assert {cmd.name for cmd in reg.visible()} == EXPECTED
    assert len(reg.visible()) == 13


def test_register_builtins_no_collision() -> None:
    reg = Registry()
    register_builtins(reg)


@pytest.mark.asyncio
async def test_register_builtins_handlers_run_on_nop_ui() -> None:
    reg = Registry()
    register_builtins(reg)
    ui = NopUI()
    for cmd in reg.visible():
        await cmd.handler(ui)


@pytest.mark.asyncio
async def test_handle_status_prints_all_keys() -> None:
    ui = RecordingUI()
    await handle_status(ui)
    assert len(ui.printed) == 1
    for key in ["Mode:", "Tokens:", "Tools:", "Memories:", "Model:", "Directory:"]:
        assert key in ui.printed[0]


@pytest.mark.asyncio
async def test_handle_compact_blocks_when_busy() -> None:
    ui = RecordingUI(idle=False)
    await handle_compact(ui)
    assert ui.errors == ["请等待当前任务完成"]
    assert not ui.compacted


@pytest.mark.asyncio
async def test_handle_do_sets_mode_and_injects() -> None:
    ui = RecordingUI()
    await handle_do(ui)
    assert ui.modes == [Mode.DEFAULT]
    assert ui.injected and ui.injected[0][0] == "/do"
