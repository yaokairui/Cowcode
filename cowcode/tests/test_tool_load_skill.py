from __future__ import annotations

import json

import pytest

from cowcode.skills.active import ActiveSkills
from cowcode.skills.catalog import Catalog
from cowcode.skills.types import Skill, SkillMeta, SkillSource, ToolSpec
from cowcode.tool import Registry
from cowcode.tool.load_skill import LoadSkillTool


def _write_skill_dir(tmp_path, name: str = "demo"):
    skill_dir = tmp_path / name
    refs = skill_dir / "references"
    refs.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Demo\n---\nFresh body\n",
        encoding="utf-8",
    )
    return skill_dir


@pytest.mark.asyncio
async def test_load_skill_unknown_returns_error(tmp_path) -> None:
    tool = LoadSkillTool(Catalog(), ActiveSkills(), Registry())

    result = await tool.execute(json.dumps({"name": "missing"}))

    assert result.is_error
    assert result.content == "unknown skill: missing"


@pytest.mark.asyncio
async def test_load_skill_activates_and_registers_tool(tmp_path) -> None:
    skill_dir = _write_skill_dir(tmp_path)
    catalog = Catalog()
    catalog.register(
        Skill(
            meta=SkillMeta("demo", "Demo"),
            prompt_body="Cached body",
            source_dir=skill_dir,
            source=SkillSource.PROJECT,
            tool_specs=[
                ToolSpec(
                    name="parse_resume",
                    description="Parse resume",
                    input_schema={"type": "object"},
                    command=["parse_resume.sh"],
                    base_dir=skill_dir,
                )
            ],
        )
    )
    active = ActiveSkills()
    registry = Registry()
    tool = LoadSkillTool(catalog, active, registry)

    result = await tool.execute(json.dumps({"name": "demo"}))

    assert not result.is_error
    assert active.names() == ["demo"]
    assert active.snapshot()[0].body == "Fresh body"
    assert registry.get("parse_resume") is not None
