"""slash 命令系统公共出口。"""

from cowcode.command.builtins import register_builtins
from cowcode.command.command import Command, Handler, Kind
from cowcode.command.dispatch import parse
from cowcode.command.registry import Registry
from cowcode.command.skills import register_skills_as_commands, remove_skill_commands
from cowcode.command.ui import NopUI, SkillSummary, UI, WorktreeAccessor, WorktreeSummary

__all__ = [
    "Command",
    "Handler",
    "Kind",
    "NopUI",
    "Registry",
    "SkillSummary",
    "UI",
    "WorktreeAccessor",
    "WorktreeSummary",
    "parse",
    "register_builtins",
    "register_skills_as_commands",
    "remove_skill_commands",
]
