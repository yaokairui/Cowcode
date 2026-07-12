from cowcode.cli import _format_mcp_status


def test_format_mcp_status() -> None:
    assert (
        _format_mcp_status(1, 2) == "Connected to 1 MCP server(s), 2 tools registered"
    )
    assert (
        _format_mcp_status(0, 0) == "Connected to 0 MCP server(s), 0 tools registered"
    )
