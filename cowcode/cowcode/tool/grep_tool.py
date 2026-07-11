"""grep tool."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from cowcode.tool import Result

_MAX_RESULTS = 100
_MAX_LINE_LENGTH = 1_000_000


class GrepTool:
    @property
    def read_only(self) -> bool:
        return True

    def name(self) -> str:
        return "grep"

    def description(self) -> str:
        return "Search text files with a Python regular expression."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Python regex pattern."},
                "path": {"type": "string", "description": "Root path. Defaults to ."},
                "glob": {"type": "string", "description": "Optional file glob."},
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
        glob_pattern = data.get("glob") or "*"
        if not isinstance(pattern, str) or not pattern:
            return Result("Missing required argument: pattern", is_error=True)
        if not isinstance(root_value, str):
            return Result("Argument path must be a string", is_error=True)
        if not isinstance(glob_pattern, str):
            return Result("Argument glob must be a string", is_error=True)

        try:
            regex = re.compile(pattern)
        except re.error as exc:
            return Result(f"Invalid regex: {exc}", is_error=True)

        root = Path(root_value)
        matches: list[str] = []
        files = root.rglob(glob_pattern) if root.is_dir() else [root]
        for file_index, path in enumerate(files, 1):
            if not path.is_file():
                continue
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    for line_number, line in enumerate(handle, 1):
                        if len(line) > _MAX_LINE_LENGTH:
                            line = line[:_MAX_LINE_LENGTH] + " [line truncated]"
                        if regex.search(line):
                            matches.append(f"{path}:{line_number}:{line.rstrip()}")
                            if len(matches) >= _MAX_RESULTS:
                                return Result("\n".join(matches) + "\n[truncated]")
            except OSError:
                continue
            if file_index % 50 == 0:
                await asyncio.sleep(0)

        if not matches:
            return Result("No matches")
        return Result("\n".join(matches))
