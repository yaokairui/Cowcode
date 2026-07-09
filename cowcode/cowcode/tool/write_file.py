"""write_file tool."""

from __future__ import annotations

import json
from pathlib import Path

from cowcode.tool import Result


class WriteFileTool:
    def name(self) -> str:
        return "write_file"

    def description(self) -> str:
        return "Create or overwrite a text file."

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write."},
                "content": {"type": "string", "description": "Text content."},
            },
            "required": ["path", "content"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args or "{}")
        except json.JSONDecodeError as exc:
            return Result(f"Invalid JSON arguments: {exc}", is_error=True)

        path_value = data.get("path")
        content = data.get("content")
        if not isinstance(path_value, str) or not path_value:
            return Result("Missing required argument: path", is_error=True)
        if not isinstance(content, str):
            return Result("Missing required argument: content", is_error=True)

        path = Path(path_value)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            return Result(f"Failed to write file {path}: {exc}", is_error=True)

        return Result(f"Wrote {path} ({len(content.encode('utf-8'))} bytes)")
