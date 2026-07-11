"""bash tool."""

from __future__ import annotations

import asyncio
import json

from cowcode.tool import Result, truncate_text


class BashTool:
    @property
    def read_only(self) -> bool:
        return False

    def name(self) -> str:
        return "bash"

    def description(self) -> str:
        return (
            "Run a shell command in the current working directory. "
            "Prefer read_file, glob, and grep for reading files, finding paths, "
            "and searching content instead of assembling shell commands."
        )

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run."}
            },
            "required": ["command"],
        }

    async def execute(self, args: str) -> Result:
        try:
            data = json.loads(args or "{}")
        except json.JSONDecodeError as exc:
            return Result(f"Invalid JSON arguments: {exc}", is_error=True)

        command = data.get("command")
        if not isinstance(command, str) or not command:
            return Result("Missing required argument: command", is_error=True)

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await proc.communicate()
        except asyncio.CancelledError:
            proc.kill()
            await proc.communicate()
            raise
        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        output = f"exit_code: {proc.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        return Result(truncate_text(output, max_lines=10_000, max_chars=30_000))
