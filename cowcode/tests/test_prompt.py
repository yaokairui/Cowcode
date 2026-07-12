"""ch05 模块化系统提示与环境采集测试。"""

from __future__ import annotations

from cowcode.environment import Environment
from cowcode.prompt import (
    Module,
    assemble_system,
    build_system_prompt,
    plan_reminder,
)


def test_module_assembly_is_ordered_extensible_and_skips_empty() -> None:
    modules = [
        Module("late", 30, "late"),
        Module("empty", 20, ""),
        Module("early", 10, "early"),
        Module("middle", 25, "middle"),
    ]
    assert assemble_system(modules) == "early\n\nmiddle\n\nlate"


def test_system_prompt_is_stable_and_contains_tool_rules() -> None:
    first = build_system_prompt()
    second = build_system_prompt()
    assert first == second
    assert "read_file" in first and "glob" in first and "grep" in first
    assert "Before editing" in first
    assert "Working directory" not in first


def test_custom_prompt_fills_optional_slot() -> None:
    text = build_system_prompt("Always answer in Chinese.")
    assert text.endswith("Always answer in Chinese.")


def test_environment_renders_separately() -> None:
    rendered = Environment(
        working_dir="/repo",
        platform="test-os",
        date="2026-07-11",
        git_status="clean",
        version="0.1.0",
        model="test-model",
    ).render()
    assert "Working directory: /repo" in rendered
    assert "Model: test-model" in rendered


def test_plan_reminders_are_tagged_and_differ() -> None:
    full = plan_reminder(True)
    concise = plan_reminder(False)
    assert full.startswith("<system-reminder>")
    assert full.endswith("</system-reminder>")
    assert "/do" in full
    assert concise != full
