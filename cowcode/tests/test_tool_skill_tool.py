from __future__ import annotations

import json
import sys

import pytest

from cowcode.tool.skill_tool import new_skill_tool


@pytest.mark.asyncio
async def test_skill_tool_executes_reference_script(tmp_path) -> None:
    refs = tmp_path / "references"
    refs.mkdir()
    script = refs / "echo_args.py"
    script.write_text(
        "import sys\nprint(sys.stdin.read())\n",
        encoding="utf-8",
    )

    tool = new_skill_tool(
        "parse_resume",
        "Parse resume",
        {"type": "object"},
        [sys.executable, str(script)],
        tmp_path,
    )

    result = await tool.execute(json.dumps({"x": 1}))

    assert not result.is_error
    assert result.content == '{"x": 1}'


@pytest.mark.asyncio
async def test_skill_tool_nonzero_is_error(tmp_path) -> None:
    script = tmp_path / "fail.py"
    script.write_text(
        "import sys\nsys.stderr.write('bad')\nsys.exit(2)\n", encoding="utf-8"
    )

    tool = new_skill_tool(
        "fail_tool",
        "Fail",
        {"type": "object"},
        [sys.executable, str(script)],
        tmp_path,
    )

    result = await tool.execute("{}")

    assert result.is_error
    assert "bad" in result.content
