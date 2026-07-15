"""SKILL.md and tool.json parsing."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

import yaml

from cowcode.skills.types import Skill, SkillMeta, SkillSource, ToolSpec

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_VALID_MODES = {"", "inline", "fork"}
_VALID_FORK_CONTEXTS = {"", "none", "recent", "full"}


def is_valid_skill_name(name: str) -> bool:
    return 1 <= len(name) <= 32 and _NAME_RE.fullmatch(name) is not None


def is_valid_tool_name(name: str) -> bool:
    return _TOOL_NAME_RE.fullmatch(name) is not None


def parse_skill_dir(dir_path: Path, source: SkillSource) -> Skill:
    path = dir_path / "SKILL.md"
    if not path.exists():
        raise FileNotFoundError(f"no SKILL.md in {dir_path}")
    data = path.read_text(encoding="utf-8")
    meta_dict, body = parse_frontmatter_and_body(data)
    meta = _build_meta(meta_dict, dir_path)
    tool_specs = (
        parse_tool_json((dir_path / "tool.json").read_bytes(), dir_path.resolve())
        if (dir_path / "tool.json").exists()
        else []
    )
    return Skill(
        meta=meta,
        prompt_body=body.strip(),
        source_dir=dir_path.resolve(),
        source=source,
        tool_specs=tool_specs,
    )


def parse_frontmatter_and_body(data: str) -> tuple[dict[str, Any], str]:
    normalized = data.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise ValueError("SKILL.md frontmatter is not closed")
    frontmatter = normalized[4:end]
    body = normalized[end + len("\n---\n") :]
    parsed = yaml.safe_load(frontmatter) or {}
    if not isinstance(parsed, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")
    return parsed, body


def parse_tool_json(data: bytes, base_dir: Path) -> list[ToolSpec]:
    raw = json.loads(data.decode("utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("tool.json must be an object")
    tools = raw.get("tools", [])
    if not isinstance(tools, list):
        raise ValueError("tool.json tools must be a list")
    specs: list[ToolSpec] = []
    for item in tools:
        if not isinstance(item, dict):
            raise ValueError("tool.json tool item must be an object")
        name = str(item.get("name", ""))
        if not is_valid_tool_name(name):
            raise ValueError(f"invalid tool name: {name}")
        command = item.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(x, str) for x in command)
        ):
            raise ValueError(f"tool {name}: command must be a non-empty string array")
        description = str(item.get("description", ""))
        input_schema = item.get("input_schema", {"type": "object"})
        if not isinstance(input_schema, dict):
            raise ValueError(f"tool {name}: input_schema must be an object")
        specs.append(
            ToolSpec(
                name=name,
                description=description,
                input_schema=input_schema,
                command=list(command),
                base_dir=base_dir,
            )
        )
    return specs


def _build_meta(meta_dict: dict[str, Any], dir_path: Path) -> SkillMeta:
    known = {field.name for field in fields(SkillMeta)}
    filtered = {key: value for key, value in meta_dict.items() if key in known}
    if "name" not in filtered or "description" not in filtered:
        raise ValueError(f"skill {dir_path}: name and description are required")
    if filtered.get("allowed_tools") is None:
        filtered["allowed_tools"] = []
    if not isinstance(filtered.get("allowed_tools", []), list) or not all(
        isinstance(item, str) for item in filtered.get("allowed_tools", [])
    ):
        raise ValueError(f"skill {dir_path}: allowed_tools must be a string array")
    meta = SkillMeta(**filtered)
    if not is_valid_skill_name(meta.name):
        raise ValueError(f"invalid skill name: {meta.name}")
    if not meta.description.strip():
        raise ValueError(f"skill {meta.name}: description is required")
    if meta.mode not in _VALID_MODES:
        print(
            f"skill {meta.name}: unknown mode {meta.mode!r}, using inline",
            file=sys.stderr,
        )
        meta.mode = "inline"
    if meta.mode == "":
        meta.mode = "inline"
    if meta.fork_context not in _VALID_FORK_CONTEXTS:
        raise ValueError(
            f"skill {meta.name}: invalid fork_context {meta.fork_context!r}"
        )
    if meta.fork_context == "":
        meta.fork_context = "none"
    return meta
