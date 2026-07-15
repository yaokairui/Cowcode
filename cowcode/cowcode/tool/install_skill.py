"""InstallSkill built-in tool."""

from __future__ import annotations

import json
from pathlib import Path

from cowcode.skills.catalog import Catalog
from cowcode.skills.install import install_from_url
from cowcode.tool import Result


class InstallSkillTool:
    def __init__(self, catalog: Catalog, work_dir: Path) -> None:
        self.catalog = catalog
        self.work_dir = work_dir

    def name(self) -> str:
        return "install_skill"

    def description(self) -> str:
        return "Install a Skill zip from an HTTP(S) URL into ~/.cowcode/skills/."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Skill zip URL"}
            },
            "required": ["source"],
        }

    @property
    def read_only(self) -> bool:
        return False

    @property
    def is_system(self) -> bool:
        return False

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args or "{}")
            source = str(data.get("source", ""))
            name = await install_from_url(source, self.catalog, self.work_dir)
        except Exception as exc:
            return Result(f"InstallSkill failed: {exc}", is_error=True)
        return Result(f"Skill {name} installed to ~/.cowcode/skills/{name}.")
