from __future__ import annotations

from pathlib import Path

from cowcode.skills.active import ActiveSkills
from cowcode.skills.render import render_body
from cowcode.skills.types import Skill, SkillMeta, SkillSource


def _skill(body: str, allowed_tools: list[str] | None = None) -> Skill:
    return Skill(
        meta=SkillMeta("demo", "Demo", allowed_tools or []),
        prompt_body=body,
        source_dir=Path("."),
        source=SkillSource.PROJECT,
    )


def test_active_skills_activate_updates_in_place() -> None:
    active = ActiveSkills()
    active.activate("a", "one")
    active.activate("b", "two")
    active.activate("a", "updated")

    assert active.names() == ["a", "b"]
    assert [(entry.name, entry.body) for entry in active.snapshot()] == [
        ("a", "updated"),
        ("b", "two"),
    ]

    active.clear()
    assert active.names() == []


def test_render_body_replaces_arguments() -> None:
    assert render_body(_skill("Hello $ARGUMENTS"), "world") == "Hello world"


def test_render_body_appends_user_request_when_no_placeholder() -> None:
    rendered = render_body(_skill("Do work"), "extra request")

    assert rendered.endswith("## User Request\n\nextra request")


def test_render_body_includes_allowed_tools_hint() -> None:
    rendered = render_body(_skill("Do work", ["bash", "read_file"]))

    assert rendered.startswith(
        "This skill is designed to use only these tools: bash, read_file."
    )
