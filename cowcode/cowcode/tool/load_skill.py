"""LoadSkill built-in tool."""

from __future__ import annotations

import json
import sys

from cowcode.skills.active import ActiveSkills
from cowcode.skills.catalog import Catalog
from cowcode.skills.parser import parse_frontmatter_and_body
from cowcode.tool import Registry, Result
from cowcode.tool.skill_tool import new_skill_tool


class LoadSkillTool:
    def __init__(
        self, catalog: Catalog, active: ActiveSkills, registry: Registry
    ) -> None:
        self.catalog = catalog
        self.active = active
        self.registry = registry

    def name(self) -> str:
        return "load_skill"

    def description(self) -> str:
        return "Activate a Skill SOP by name and register its specialized tools."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Skill name"}},
            "required": ["name"],
        }

    @property
    def read_only(self) -> bool:
        return True

    @property
    def is_system(self) -> bool:
        return True

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args or "{}")
        except json.JSONDecodeError as exc:
            return Result(f"invalid JSON: {exc}", is_error=True)
        name = str(data.get("name", ""))
        skill = self.catalog.get(name)
        if skill is None:
            return Result(f"unknown skill: {name}", is_error=True)
        body = skill.prompt_body
        try:
            _, body = parse_frontmatter_and_body(
                (skill.source_dir / "SKILL.md").read_text(encoding="utf-8")
            )
            body = body.strip()
        except Exception as exc:
            print(f"skill {name}: failed to reread SKILL.md: {exc}", file=sys.stderr)
        self.active.activate(skill.meta.name, body)
        for spec in skill.tool_specs:
            self.registry.register_skill_tool(
                new_skill_tool(
                    spec.name,
                    spec.description,
                    spec.input_schema,
                    spec.command,
                    spec.base_dir,
                )
            )
        return Result(
            f"Skill {name} activated. SOP pinned to env context. "
            f"{len(skill.tool_specs)} specialized tools registered."
        )
