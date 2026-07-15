"""glob tool."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from cowcode.tool import Result
from cowcode.tool.ctx import resolve_path


class GlobTool:
    @property
    def read_only(self) -> bool:
        return True

    def name(self) -> str:
        return "glob"

    def description(self) -> str:
        return "Find files by a glob pattern."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern."},
                "path": {"type": "string", "description": "Root path. Defaults to ."},
            },
            "required": ["pattern"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args or "{}")
        except json.JSONDecodeError as exc:
            return Result(f"Invalid JSON arguments: {exc}", is_error=True)

        pattern = data.get("pattern")
        root_value = data.get("path") or "."
        if not isinstance(pattern, str) or not pattern:
            return Result("Missing required argument: pattern", is_error=True)
        if not isinstance(root_value, str):
            return Result("Argument path must be a string", is_error=True)

        root = Path(resolve_path(root_value))
        try:
            matches: list[str] = []
            for index, candidate in enumerate(root.glob(pattern), 1):
                if candidate.is_file():
                    matches.append(str(candidate))
                if index % 100 == 0:
                    await asyncio.sleep(0)
            matches = sorted(matches)
        except OSError as exc:
            return Result(f"Glob failed: {exc}", is_error=True)

        if not matches:
            return Result("No matches")
        output = "\n".join(matches[:100])
        if len(matches) > 100:
            output += "\n[truncated]"
        return Result(output)
