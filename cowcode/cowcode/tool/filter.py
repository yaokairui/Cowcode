"""SubAgent tool filtering."""

from __future__ import annotations

from dataclasses import dataclass, field

ALL_AGENT_DISALLOWED_TOOLS: list[str] = [
    "Agent",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskUpdate",
    "SendMessage",
]
TEAMMATE_EXTRA_TOOLS: list[str] = [
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskUpdate",
    "SendMessage",
]
CUSTOM_AGENT_DISALLOWED_TOOLS: list[str] = []
ASYNC_AGENT_ALLOWED_TOOLS: list[str] = [
    "read_file",
    "write_file",
    "edit_file",
    "glob",
    "grep",
    "bash",
    "load_skill",
    "install_skill",
]


@dataclass
class FilterParams:
    all: list[str]
    source: int
    background: bool
    allowed: list[str] = field(default_factory=list)
    disallowed: list[str] = field(default_factory=list)
    keep_agent: bool = False
    teammate: bool = False


def apply_agent_tool_filter(params: FilterParams) -> list[str]:
    names = list(params.all)
    disallowed = set(ALL_AGENT_DISALLOWED_TOOLS)
    if params.teammate:
        disallowed.difference_update(TEAMMATE_EXTRA_TOOLS)
    if params.keep_agent:
        disallowed.discard("Agent")
    names = [name for name in names if name not in disallowed]
    if params.source >= 2 and CUSTOM_AGENT_DISALLOWED_TOOLS:
        names = [name for name in names if name not in CUSTOM_AGENT_DISALLOWED_TOOLS]
    if params.background:
        names = [
            name
            for name in names
            if name in ASYNC_AGENT_ALLOWED_TOOLS
            or is_mcp_or_skill(name)
            or (params.keep_agent and name == "Agent")
        ]
    if params.disallowed:
        blocked = set(params.disallowed)
        names = [name for name in names if name not in blocked]
    if params.allowed:
        allowed = set(params.allowed)
        names = [name for name in names if name in allowed]
    return names


def is_mcp_or_skill(name: str) -> bool:
    return name.startswith("mcp__")
