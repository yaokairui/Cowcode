"""把 Skill 注册为 slash prompt 命令。"""

from __future__ import annotations

from typing import Protocol

from cowcode.command.command import Command, Kind
from cowcode.command.registry import Registry
from cowcode.command.ui import SkillSummary, UI


class SkillRunner(Protocol):
    async def execute(self, ui: UI, name: str, args: str = "") -> None: ...


def register_skills_as_commands(
    registry: Registry,
    skills: list[SkillSummary],
    executor: SkillRunner,
) -> None:
    """把 catalog 中的 Skill 暴露为 /name 命令。"""

    for item in sorted(skills, key=lambda skill: skill.name):
        if registry.lookup(item.name) is not None:
            continue

        async def _handler(ui: UI, skill_name: str = item.name) -> None:
            await executor.execute(ui, skill_name, "")

        registry.register(
            Command(
                name=item.name,
                description=f"{item.description} [skill]",
                kind=Kind.PROMPT,
                handler=_handler,
                is_skill=True,
            )
        )


def remove_skill_commands(registry: Registry) -> None:
    registry.remove_if(lambda command: command.is_skill)
