"""Built-in tool system for Cowcode."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from cowcode.session import ToolDefinition

DEFAULT_TIMEOUT = 30.0

__all__ = [
    "DEFAULT_TIMEOUT",
    "Registry",
    "Result",
    "Tool",
    "new_default_registry",
    "truncate_text",
]


@dataclass
class Result:
    """工具执行结果，错误也以值返回。"""

    content: str
    is_error: bool = False


@runtime_checkable
class Tool(Protocol):
    """统一工具抽象。"""

    def name(self) -> str: ...

    def description(self) -> str: ...

    def parameters(self) -> dict[str, Any]: ...

    @property
    def read_only(self) -> bool:
        """True=只读工具，可并发执行 & Plan Mode 放行。"""
        ...

    async def execute(self, args: str) -> Result: ...


class Registry:
    """工具注册中心。"""

    def __init__(self) -> None:
        self._order: list[str] = []
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.name()
        if name not in self._tools:
            self._order.append(name)
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def count(self) -> int:
        return len(self._tools)

    def definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=name,
                description=self._tools[name].description(),
                input_schema=self._tools[name].parameters(),
            )
            for name in self._order
        ]

    def read_only_definitions(self) -> list[ToolDefinition]:
        """Plan Mode：仅导出 read_only==True 的工具定义，保留注册顺序。"""
        return [
            ToolDefinition(
                name=name,
                description=self._tools[name].description(),
                input_schema=self._tools[name].parameters(),
            )
            for name in self._order
            if self._tools[name].read_only is True
        ]

    def is_read_only(self, name: str) -> bool:
        """分批判定工具是否为只读；未知工具返回 False。"""
        t = self.get(name)
        return t is not None and t.read_only

    async def execute(
        self, name: str, args: str, timeout: float = DEFAULT_TIMEOUT
    ) -> Result:
        tool = self.get(name)
        if tool is None:
            return Result(content=f"Unknown tool: {name}", is_error=True)
        try:
            return await asyncio.wait_for(tool.execute(args or "{}"), timeout=timeout)
        except TimeoutError:
            return Result(
                content=f"Tool {name} timed out after {timeout:.1f}s",
                is_error=True,
            )
        except Exception as exc:
            return Result(content=f"Tool {name} failed: {exc}", is_error=True)


def truncate_text(text: str, max_lines: int, max_chars: int) -> str:
    """按行数和字符数截断工具结果。"""
    truncated = False
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    output = "\n".join(lines)
    if len(output) > max_chars:
        output = output[:max_chars]
        truncated = True
    if truncated:
        output = output.rstrip() + "\n[truncated]"
    return output


def new_default_registry() -> Registry:
    """构造默认工具集——含 6 个文件工具 + AskUserQuestion 澄清工具。"""
    from cowcode.tool.ask_user_question import AskUserQuestionTool
    from cowcode.tool.bash import BashTool
    from cowcode.tool.edit_file import EditFileTool
    from cowcode.tool.glob_tool import GlobTool
    from cowcode.tool.grep_tool import GrepTool
    from cowcode.tool.read_file import ReadFileTool
    from cowcode.tool.write_file import WriteFileTool

    registry = Registry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    registry.register(BashTool())
    registry.register(GlobTool())
    registry.register(GrepTool())
    registry.register(AskUserQuestionTool())
    return registry
