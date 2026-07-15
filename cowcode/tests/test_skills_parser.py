from __future__ import annotations

import json

import pytest

from cowcode.skills.parser import parse_skill_dir
from cowcode.skills.types import SkillSource


def _write_skill(path, frontmatter: str, body: str = "Body") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\n{frontmatter}\n---\n{body}\n", encoding="utf-8"
    )


def test_parse_skill_dir_minimal(tmp_path) -> None:
    skill_dir = tmp_path / "demo"
    _write_skill(skill_dir, "name: demo\ndescription: Demo skill")

    skill = parse_skill_dir(skill_dir, SkillSource.PROJECT)

    assert skill.meta.name == "demo"
    assert skill.meta.description == "Demo skill"
    assert skill.prompt_body == "Body"
    assert skill.tool_specs == []


def test_parse_skill_dir_invalid_name(tmp_path) -> None:
    skill_dir = tmp_path / "bad"
    _write_skill(skill_dir, "name: BadName\ndescription: Bad skill")

    with pytest.raises(ValueError, match="invalid skill name"):
        parse_skill_dir(skill_dir, SkillSource.PROJECT)


def test_parse_skill_dir_with_tool_json_allows_existing_tool_style(tmp_path) -> None:
    skill_dir = tmp_path / "resume"
    _write_skill(
        skill_dir,
        "name: resume\ndescription: Resume parser\nallowed_tools:\n  - parse_resume",
    )
    (skill_dir / "tool.json").write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "name": "parse_resume",
                        "description": "Parse a resume",
                        "input_schema": {"type": "object"},
                        "command": ["parse_resume.sh"],
                    },
                    {
                        "name": "AskUserQuestion",
                        "description": "Ask a question",
                        "input_schema": {"type": "object"},
                        "command": ["ask.sh"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    skill = parse_skill_dir(skill_dir, SkillSource.PROJECT)

    assert [tool.name for tool in skill.tool_specs] == [
        "parse_resume",
        "AskUserQuestion",
    ]


def test_parse_skill_dir_no_skill_md(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_skill_dir(tmp_path / "missing", SkillSource.USER)
