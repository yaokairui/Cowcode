"""Adapter from Skill tool specs to Cowcode tools."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cowcode.tool import Result


@dataclass(slots=True)
class SkillTool:
    _name: str
    _description: str
    _parameters: dict[str, Any]
    _command: list[str]
    _base_dir: Path

    def name(self) -> str:
        return self._name

    def description(self) -> str:
        return self._description

    def parameters(self) -> dict[str, Any]:
        return self._parameters

    @property
    def read_only(self) -> bool:
        return False

    @property
    def is_system(self) -> bool:
        return False

    async def execute(self, args: str) -> Result:
        command = list(self._command)
        first = Path(command[0])
        if not first.is_absolute():
            first = self._base_dir / "references" / first
        command[0] = str(first)
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=self._base_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=(args or "{}").encode("utf-8")), timeout=30.0
        )
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            text = err or out or f"tool exited with code {proc.returncode}"
            return Result(text, is_error=True)
        return Result(out)


def new_skill_tool(
    name: str,
    description: str,
    input_schema: dict[str, Any],
    command: list[str],
    base_dir: Path,
) -> SkillTool:
    return SkillTool(name, description, input_schema, command, base_dir)
