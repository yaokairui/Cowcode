"""内置 slash 命令注册。"""

from __future__ import annotations

from cowcode.command.builtin_local import (
    handle_memory,
    handle_permission,
    handle_session,
    handle_status,
    make_help_handler,
)
from cowcode.command.builtin_prompt import handle_do, handle_review
from cowcode.command.builtin_ui import (
    handle_clear,
    handle_compact,
    handle_exit,
    handle_plan,
    handle_resume,
)
from cowcode.command.command import Command, Kind
from cowcode.command.registry import Registry


def register_builtins(reg: Registry) -> None:
    """注册全部内置命令。"""

    commands = [
        Command("clear", "清空当前会话并开启新会话", Kind.UI, handle_clear),
        Command("compact", "手动压缩当前上下文", Kind.UI, handle_compact),
        Command("do", "批准计划并开始执行", Kind.PROMPT, handle_do),
        Command("exit", "退出 Cowcode", Kind.UI, handle_exit),
        Command("help", "显示可用命令", Kind.LOCAL, make_help_handler(reg)),
        Command("memory", "显示已加载记忆文件", Kind.LOCAL, handle_memory),
        Command("permission", "显示当前权限模式", Kind.LOCAL, handle_permission),
        Command("plan", "切换到计划模式", Kind.UI, handle_plan),
        Command("resume", "恢复历史会话", Kind.UI, handle_resume),
        Command("review", "请求审查当前上下文代码", Kind.PROMPT, handle_review),
        Command("session", "显示当前会话信息", Kind.LOCAL, handle_session),
        Command("status", "显示当前运行状态", Kind.LOCAL, handle_status),
    ]
    for cmd in commands:
        reg.register(cmd)
