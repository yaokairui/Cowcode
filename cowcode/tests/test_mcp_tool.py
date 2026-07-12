from __future__ import annotations

import asyncio
import json

import mcp.types as mtypes
import pytest

from cowcode.mcp import tool as tool_module
from cowcode.mcp.tool import McpTool, adapt_tool


class StubSession:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    async def call_tool(self, name, arguments):
        if self.error:
            raise self.error
        return self.result


def make_tool(**overrides):
    values = {
        "name": "echo",
        "description": "Echo",
        "inputSchema": {"type": "object"},
    }
    values.update(overrides)
    return mtypes.Tool(**values)


def test_adapt_tool_fields_and_name(capsys) -> None:
    session = StubSession()
    adapted = adapt_tool(
        "demo",
        make_tool(
            description="",
            inputSchema={},
            annotations=mtypes.ToolAnnotations(readOnlyHint=True),
        ),
        session,
    )

    assert isinstance(adapted, McpTool)
    assert adapted.name() == "mcp__demo__echo"
    assert adapted.parameters() == {"type": "object"}
    assert adapted.read_only is True
    assert "demo" in adapted.description()
    assert adapt_tool("bad.name", make_tool(), session) is None
    assert "illegal characters" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_execute_collects_text_and_maps_error(capsys) -> None:
    tool_module._non_text_warn_once.clear()
    result = mtypes.CallToolResult(
        content=[
            mtypes.TextContent(type="text", text="first"),
            mtypes.ImageContent(type="image", data="AA==", mimeType="image/png"),
            mtypes.TextContent(type="text", text="second"),
        ],
        isError=True,
    )
    tool = adapt_tool("demo", make_tool(), StubSession(result))
    assert tool is not None

    first = await tool.execute(json.dumps({"value": 1}))
    second = await tool.execute("{}")

    assert first.content == "first\nsecond"
    assert first.is_error is True
    assert second.content == "first\nsecond"
    assert capsys.readouterr().err.count("non-text") == 1


@pytest.mark.asyncio
async def test_execute_failure_and_timeout(monkeypatch) -> None:
    failed = adapt_tool("demo", make_tool(), StubSession(error=RuntimeError("broken")))
    assert failed is not None
    failure = await failed.execute("{}")
    assert failure.is_error is True
    assert "broken" in failure.content

    class BlockingSession:
        async def call_tool(self, name, arguments):
            await asyncio.Event().wait()

    monkeypatch.setattr(tool_module, "call_timeout", 0.01)
    blocked = adapt_tool("demo", make_tool(), BlockingSession())
    assert blocked is not None
    timeout = await blocked.execute("{}")
    assert timeout.is_error is True
    assert "超时" in timeout.content
