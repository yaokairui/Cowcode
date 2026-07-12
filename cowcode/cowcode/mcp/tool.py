"""远端 MCP 工具适配。"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from typing import Any, Protocol

import mcp.types as mtypes

from cowcode.tool import Result

call_timeout: float = 30.0
_VALID_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
_non_text_warn_once: set[str] = set()


class CallerSession(Protocol):
    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None
    ) -> mtypes.CallToolResult: ...


@dataclass
class McpTool:
    full_name: str
    remote_name: str
    tool_description: str
    input_schema: dict[str, Any]
    read_only: bool
    caller: CallerSession

    def name(self) -> str:
        return self.full_name

    def description(self) -> str:
        return self.tool_description

    def parameters(self) -> dict[str, Any]:
        return dict(self.input_schema)

    async def execute(self, args: str) -> Result:
        try:
            parsed = json.loads(args or "{}")
            if not isinstance(parsed, dict):
                return Result(content="MCP 工具参数必须是 JSON 对象", is_error=True)
        except (TypeError, json.JSONDecodeError) as exc:
            return Result(content=f"MCP 工具参数解析失败: {exc}", is_error=True)

        try:
            result = await asyncio.wait_for(
                self.caller.call_tool(self.remote_name, parsed or None),
                timeout=call_timeout,
            )
        except asyncio.TimeoutError:
            return Result(
                content=f"MCP 工具调用超时 ({call_timeout:g}s)", is_error=True
            )
        except Exception as exc:
            return Result(content=f"MCP 工具调用失败: {exc}", is_error=True)

        texts: list[str] = []
        has_non_text = False
        for block in result.content:
            if isinstance(block, mtypes.TextContent):
                texts.append(block.text)
            else:
                has_non_text = True
        if has_non_text and self.full_name not in _non_text_warn_once:
            _non_text_warn_once.add(self.full_name)
            print(
                f"[mcp] warn: tool {self.full_name} returned non-text content blocks (dropped)",
                file=sys.stderr,
            )
        return Result(content="\n".join(texts), is_error=bool(result.isError))


def adapt_tool(
    server_name: str, tool: mtypes.Tool, session: CallerSession
) -> McpTool | None:
    """把 SDK 工具定义转换为 Cowcode 工具。"""

    full_name = f"mcp__{server_name}__{tool.name}"
    if _VALID_NAME.fullmatch(full_name) is None:
        print(
            f"[mcp] warn: skip tool {full_name}: name contains illegal characters",
            file=sys.stderr,
        )
        return None
    schema = dict(tool.inputSchema) if tool.inputSchema else {"type": "object"}
    annotations = getattr(tool, "annotations", None)
    return McpTool(
        full_name=full_name,
        remote_name=tool.name,
        tool_description=tool.description
        or f"来自 MCP server {server_name} 的工具 {tool.name}",
        input_schema=schema,
        read_only=bool(annotations and annotations.readOnlyHint is True),
        caller=session,
    )
