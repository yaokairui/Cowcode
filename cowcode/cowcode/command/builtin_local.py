"""纯本地 slash 命令。"""

from __future__ import annotations

from cowcode.command.command import Handler
from cowcode.command.registry import Registry
from cowcode.command.ui import UI


def make_help_handler(reg: Registry) -> Handler:
    async def _handler(ui: UI) -> None:
        commands = reg.visible()
        width = max((len(cmd.name) for cmd in commands), default=0)
        lines = [f"/{cmd.name.ljust(width)}  {cmd.description}" for cmd in commands]
        ui.println("\n".join(lines))

    return _handler


async def handle_status(ui: UI) -> None:
    rows = [
        ("Mode:", str(ui.mode())),
        ("Tokens:", f"{ui.usage_in()} in / {ui.usage_out()} out"),
        ("Tools:", f"{ui.tool_count()} enabled"),
        ("Memories:", f"{len(ui.memory_files())} files"),
        ("Model:", ui.model_name()),
        ("Directory:", ui.cwd()),
    ]
    width = max(len(key) for key, _ in rows)
    body = "MewCode Status\n\n" + "\n".join(
        f"{key.ljust(width)} {value}" for key, value in rows
    )
    ui.println(body)


async def handle_memory(ui: UI) -> None:
    files = ui.memory_files()
    ui.println("\n".join(files) if files else "无已加载的记忆文件")


async def handle_permission(ui: UI) -> None:
    ui.println(str(ui.mode()))


async def handle_session(ui: UI) -> None:
    ui.println(f"Session: {ui.session_id()}\nPath: {ui.session_path()}")
