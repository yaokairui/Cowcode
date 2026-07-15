"""edit_file tool."""

from __future__ import annotations

import json
from pathlib import Path

from cowcode.tool import Result
from cowcode.tool.ctx import resolve_path


class EditFileTool:
    @property
    def read_only(self) -> bool:
        return False

    def name(self) -> str:
        return "edit_file"

    def description(self) -> str:
        return (
            "Replace one unique text snippet in a file. Read the target first with "
            "read_file and ensure old_string matches exactly once."
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to edit."},
                "old_string": {
                    "type": "string",
                    "description": "Existing text. Must match exactly once.",
                },
                "new_string": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old_string", "new_string"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args or "{}")
        except json.JSONDecodeError as exc:
            return Result(f"Invalid JSON arguments: {exc}", is_error=True)

        path_value = data.get("path")
        old = data.get("old_string")
        new = data.get("new_string")
        if not isinstance(path_value, str) or not path_value:
            return Result("Missing required argument: path", is_error=True)
        if not isinstance(old, str) or old == "":
            return Result("Missing required argument: old_string", is_error=True)
        if not isinstance(new, str):
            return Result("Missing required argument: new_string", is_error=True)

        path = Path(resolve_path(path_value))
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return Result(f"Failed to read file {path}: {exc}", is_error=True)

        count = content.count(old)
        if count == 0:
            return Result("No match found for old_string", is_error=True)
        if count > 1:
            return Result(
                f"Matched {count} locations; old_string is not unique. Provide more context.",
                is_error=True,
            )

        try:
            path.write_text(content.replace(old, new, 1), encoding="utf-8")
        except OSError as exc:
            return Result(f"Failed to write file {path}: {exc}", is_error=True)

        return Result(f"Edited {path}")
