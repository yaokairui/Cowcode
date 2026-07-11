from __future__ import annotations

import json

import pytest

from cowcode.tool import new_default_registry
from cowcode.tool.edit_file import EditFileTool


@pytest.mark.asyncio
async def test_registry_definitions_are_ordered() -> None:
    registry = new_default_registry()

    assert [definition.name for definition in registry.definitions()] == [
        "read_file",
        "write_file",
        "edit_file",
        "bash",
        "glob",
        "grep",
    ]
    assert registry.get("read_file") is not None
    assert registry.get("missing") is None


@pytest.mark.asyncio
async def test_read_file_success_and_missing(tmp_path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("hello\nworld", encoding="utf-8")
    registry = new_default_registry()

    ok = await registry.execute("read_file", json.dumps({"path": str(path)}))
    missing = await registry.execute(
        "read_file", json.dumps({"path": str(tmp_path / "nope.txt")})
    )

    assert not ok.is_error
    assert "     1\thello" in ok.content
    assert missing.is_error
    assert "File not found" in missing.content


@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(tmp_path) -> None:
    path = tmp_path / "nested" / "file.txt"
    registry = new_default_registry()

    result = await registry.execute(
        "write_file", json.dumps({"path": str(path), "content": "content"})
    )

    assert not result.is_error
    assert path.read_text(encoding="utf-8") == "content"


@pytest.mark.asyncio
async def test_edit_file_match_counts(tmp_path) -> None:
    path = tmp_path / "edit.txt"
    tool = EditFileTool()

    path.write_text("alpha beta", encoding="utf-8")
    ok = await tool.execute(
        json.dumps({"path": str(path), "old_string": "beta", "new_string": "gamma"})
    )
    assert not ok.is_error
    assert path.read_text(encoding="utf-8") == "alpha gamma"

    zero = await tool.execute(
        json.dumps({"path": str(path), "old_string": "missing", "new_string": "x"})
    )
    assert zero.is_error
    assert "No match" in zero.content

    path.write_text("same same", encoding="utf-8")
    many = await tool.execute(
        json.dumps({"path": str(path), "old_string": "same", "new_string": "x"})
    )
    assert many.is_error
    assert "Matched 2" in many.content


@pytest.mark.asyncio
async def test_bash_glob_and_grep(tmp_path) -> None:
    path = tmp_path / "a.py"
    path.write_text("print('needle')\n", encoding="utf-8")
    registry = new_default_registry()

    bash = await registry.execute("bash", json.dumps({"command": "echo hi"}))
    glob = await registry.execute(
        "glob", json.dumps({"path": str(tmp_path), "pattern": "**/*.py"})
    )
    grep = await registry.execute(
        "grep",
        json.dumps({"path": str(tmp_path), "glob": "*.py", "pattern": "needle"}),
    )

    assert "exit_code: 0" in bash.content
    assert "hi" in bash.content
    assert str(path) in glob.content
    assert "needle" in grep.content


@pytest.mark.asyncio
async def test_registry_timeout() -> None:
    registry = new_default_registry()

    result = await registry.execute(
        "bash",
        json.dumps({"command": 'python -c "import time; time.sleep(2)"'}),
        timeout=0.1,
    )

    assert result.is_error
    assert "timed out" in result.content
