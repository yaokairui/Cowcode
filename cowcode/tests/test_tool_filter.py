from __future__ import annotations

from cowcode.tool.filter import (
    ALL_AGENT_DISALLOWED_TOOLS,
    ASYNC_AGENT_ALLOWED_TOOLS,
    CUSTOM_AGENT_DISALLOWED_TOOLS,
    FilterParams,
    apply_agent_tool_filter,
    is_mcp_or_skill,
)


def test_constants() -> None:
    assert ALL_AGENT_DISALLOWED_TOOLS == ["Agent"]
    assert CUSTOM_AGENT_DISALLOWED_TOOLS == []
    assert "bash" in ASYNC_AGENT_ALLOWED_TOOLS


def test_filter_removes_agent_by_default() -> None:
    assert apply_agent_tool_filter(FilterParams(all=["read_file", "Agent"], source=0, background=False)) == ["read_file"]


def test_background_keeps_basic_and_mcp_tools() -> None:
    result = apply_agent_tool_filter(
        FilterParams(
            all=["read_file", "TaskList", "mcp__server__tool", "Agent"],
            source=0,
            background=True,
        )
    )

    assert result == ["read_file", "mcp__server__tool"]


def test_allowed_and_disallowed_filters() -> None:
    result = apply_agent_tool_filter(
        FilterParams(
            all=["read_file", "grep", "bash"],
            source=0,
            background=False,
            allowed=["read_file", "bash"],
            disallowed=["bash"],
        )
    )

    assert result == ["read_file"]


def test_is_mcp_or_skill() -> None:
    assert is_mcp_or_skill("mcp__x__y") is True
    assert is_mcp_or_skill("read_file") is False
