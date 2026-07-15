"""Skill body rendering."""

from __future__ import annotations

from cowcode.skills.types import Skill


def render_body(skill: Skill, args: str = "") -> str:
    body = skill.prompt_body
    if "$ARGUMENTS" in body:
        body = body.replace("$ARGUMENTS", args or "")
    elif args.strip():
        body = body.rstrip() + "\n\n## User Request\n\n" + args
    if skill.meta.allowed_tools:
        allowed = ", ".join(skill.meta.allowed_tools)
        body = (
            f"This skill is designed to use only these tools: {allowed}. "
            "Prefer them over other tools when possible.\n\n---\n\n" + body
        )
    return body
