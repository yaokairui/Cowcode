"""slash 命令系统公共出口。"""

from cowcode.command.builtins import register_builtins
from cowcode.command.command import Command, Handler, Kind
from cowcode.command.dispatch import parse
from cowcode.command.registry import Registry
from cowcode.command.ui import NopUI, UI

__all__ = [
    "Command",
    "Handler",
    "Kind",
    "NopUI",
    "Registry",
    "UI",
    "parse",
    "register_builtins",
]
