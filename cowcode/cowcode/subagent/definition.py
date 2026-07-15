"""SubAgent role definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Literal

from cowcode.permission import Mode


class Source(IntEnum):
    """Agent definition source. Higher value wins on name conflict."""

    BUILTIN = 0
    USER = 1
    PROJECT = 2
    PLUGIN = 3

    def __str__(self) -> str:
        return {
            Source.BUILTIN: "builtin",
            Source.USER: "user",
            Source.PROJECT: "project",
            Source.PLUGIN: "plugin",
        }.get(self, "unknown")


@dataclass
class Definition:
    """One Markdown + YAML frontmatter SubAgent role definition."""

    name: str
    description: str
    tools: list[str] = field(default_factory=list)
    disallowed_tools: list[str] = field(default_factory=list)
    model: Literal["haiku", "sonnet", "opus", "inherit"] = "inherit"
    max_turns: int = 0
    permission_mode: Mode = Mode.DEFAULT
    dont_ask: bool = False
    background: bool = False
    system_prompt: str = ""
    file_path: str = ""
    source: Source = Source.BUILTIN

    def is_fork(self) -> bool:
        return self.name == "__fork__"
