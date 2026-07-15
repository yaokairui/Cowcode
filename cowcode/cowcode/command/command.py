"""slash 命令类型定义。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cowcode.command.ui import UI


class Kind(Enum):
    """命令执行类型。"""

    LOCAL = "local"
    UI = "ui"
    PROMPT = "prompt"


Handler = Callable[["UI"], Awaitable[None]]


@dataclass(slots=True)
class Command:
    """一条已注册 slash 命令。"""

    name: str
    description: str
    kind: Kind
    handler: Handler
    aliases: list[str] = field(default_factory=list)
    hidden: bool = False
    is_skill: bool = False
