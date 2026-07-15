"""Hook 规则数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from cowcode.hook.event import Event
from cowcode.permission.matcher import Matcher

Payload = dict[str, Any]


class CombineMode(str, Enum):
    ALL_OF = "all_of"
    ANY_OF = "any_of"


class ActionType(str, Enum):
    SHELL = "shell"
    PROMPT = "prompt"
    HTTP = "http"
    SUBAGENT = "subagent"


@dataclass(frozen=True)
class AtomCondition:
    field: str
    matcher: Matcher


@dataclass(frozen=True)
class Condition:
    mode: CombineMode
    atoms: list[AtomCondition] = field(default_factory=list)


@dataclass(frozen=True)
class ShellAction:
    command: str


@dataclass(frozen=True)
class PromptAction:
    text: str


@dataclass(frozen=True)
class HttpAction:
    url: str
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None


@dataclass(frozen=True)
class SubagentAction:
    agent_name: str
    prompt: str


Action = ShellAction | PromptAction | HttpAction | SubagentAction


@dataclass(frozen=True)
class Rule:
    name: str
    event: Event
    condition: Condition | None
    action_type: ActionType
    action: Action
    only_once: bool = False
    asyncio_mode: bool = False
    timeout: float = 30.0
    source: str = ""
