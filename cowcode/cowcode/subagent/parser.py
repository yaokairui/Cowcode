"""Markdown + YAML frontmatter parser for SubAgent definitions."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

from cowcode.permission import Mode
from cowcode.subagent.definition import Definition, Source

UTF8_BOM = "﻿"
AGENT_NAME_REGEX = re.compile(r"^[A-Za-z][A-Za-z0-9\-_]{0,31}$")
_VALID_MODELS = {"", "inherit", "haiku", "sonnet", "opus"}
_VALID_ISOLATION = {"", "worktree"}


def parse_frontmatter_and_body(data: str) -> tuple[dict[str, Any], str]:
    normalized = data.replace("\r\n", "\n")
    if normalized.startswith(UTF8_BOM):
        normalized = normalized[len(UTF8_BOM) :]
    if not normalized.startswith("---\n"):
        raise ValueError("agent definition must start with YAML frontmatter")
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise ValueError("agent definition frontmatter is not closed")
    frontmatter = normalized[4:end]
    body = normalized[end + len("\n---\n") :]
    parsed = yaml.safe_load(frontmatter) or {}
    if not isinstance(parsed, dict):
        raise ValueError("agent definition frontmatter must be a mapping")
    return parsed, body.lstrip("\n")


def parse_definition(data: bytes, file_path: str, source: Source) -> Definition:
    text = data.decode("utf-8-sig")
    fm, body = parse_frontmatter_and_body(text)

    name = str(fm.get("name", "")).strip()
    if not name or AGENT_NAME_REGEX.fullmatch(name) is None:
        raise ValueError(f"agent {file_path}: invalid name {name!r}")

    description = str(fm.get("description", "")).strip()
    if not description:
        raise ValueError(f"agent {name}: description is required")

    tools = _str_list(fm.get("tools"), "tools", name)
    disallowed_tools = _str_list(fm.get("disallowedTools"), "disallowedTools", name)

    model = str(fm.get("model") or "inherit").strip()
    if model not in _VALID_MODELS:
        print(
            f"agent {name}: unknown model {model!r}, defaulting to inherit",
            file=sys.stderr,
        )
        model = "inherit"
    if not model:
        model = "inherit"

    max_turns = int(fm.get("maxTurns") or 0)
    permission_mode, dont_ask = _parse_permission_mode(
        str(fm.get("permissionMode") or "default"), name
    )
    isolation = str(fm.get("isolation") or "").strip()
    if isolation not in _VALID_ISOLATION:
        print(
            f"agent {name}: unknown isolation {isolation!r}, defaulting to none",
            file=sys.stderr,
        )
        isolation = ""

    return Definition(
        name=name,
        description=description,
        tools=tools,
        disallowed_tools=disallowed_tools,
        model=model,  # type: ignore[arg-type]
        max_turns=max_turns,
        permission_mode=permission_mode,
        dont_ask=dont_ask,
        background=bool(fm.get("background") or False),
        isolation=isolation,
        system_prompt=body,
        file_path=file_path,
        source=source,
    )


def parse_file(path: str | Path, source: Source) -> Definition:
    p = Path(path)
    return parse_definition(p.read_bytes(), str(p), source)


def _str_list(value: object, field: str, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"agent {name}: {field} must be a string array")
    return list(value)


def _parse_permission_mode(value: str, name: str) -> tuple[Mode, bool]:
    raw = value.strip()
    if raw == "dontAsk":
        return Mode.DEFAULT, True
    mode, ok = Mode.parse(raw or "default")
    if not ok:
        print(
            f"agent {name}: unknown permissionMode {raw!r}, defaulting to default",
            file=sys.stderr,
        )
        return Mode.DEFAULT, False
    return mode, False
