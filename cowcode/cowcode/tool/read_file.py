"""read_file tool."""

from __future__ import annotations

import json
from pathlib import Path

from cowcode.tool import Result, truncate_text


class ReadFileTool:
    @property
    def read_only(self) -> bool:
        return True

    def name(self) -> str:
        return "read_file"

    def description(self) -> str:
        return "Read a text file and return numbered lines."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path of the file to read.",
                }
            },
            "required": ["path"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args or "{}")
        except json.JSONDecodeError as exc:
            return Result(f"Invalid JSON arguments: {exc}", is_error=True)

        path_value = data.get("path")
        if not isinstance(path_value, str) or not path_value:
            return Result("Missing required argument: path", is_error=True)

        path = Path(path_value)
        if not path.exists():
            return Result(f"File not found: {path}", is_error=True)
        if path.is_dir():
            return Result(f"Path is a directory: {path}", is_error=True)

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return Result(f"Failed to read file {path}: {exc}", is_error=True)

        numbered = "\n".join(
            f"{line_number:6d}\t{line}"
            for line_number, line in enumerate(text.splitlines(), 1)
        )
        return Result(truncate_text(numbered, max_lines=2000, max_chars=256_000))
