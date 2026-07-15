"""Prompt rendering helpers for Skills."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SkillCatalogItem:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class ActiveSkillEntry:
    name: str
    body: str


def render_skills_catalog(items: list[SkillCatalogItem]) -> str:
    if not items:
        return ""
    lines = ["## Available Skills", ""]
    lines.extend(f"- {item.name}: {item.description}" for item in items)
    lines.extend(
        [
            "",
            'Call the load_skill tool with {"name": "<skill_name>"} '
            "to activate a skill's full SOP and specialized tools before executing it.",
        ]
    )
    return "\n".join(lines)


def render_active_skills_block(entries: list[ActiveSkillEntry]) -> str:
    if not entries:
        return ""
    parts = ["## Active Skills"]
    for entry in entries:
        parts.append(f"### Skill: {entry.name}\n\n{entry.body.strip()}")
    return "\n\n".join(parts)
