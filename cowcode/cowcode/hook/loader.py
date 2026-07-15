"""Hook YAML 加载器。"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

from cowcode.hook.engine import Engine
from cowcode.hook.event import is_blocking, parse_event
from cowcode.hook.rule import (
    ActionType,
    AtomCondition,
    CombineMode,
    Condition,
    HttpAction,
    PromptAction,
    Rule,
    ShellAction,
    SubagentAction,
)
from cowcode.permission.matcher import compile_matcher


def load(project_root: str | Path) -> Engine:
    """加载项目级与用户级 hooks.yaml。"""

    candidates = [
        Path(project_root) / ".cowcode" / "hooks.yaml",
        Path.home() / ".cowcode" / "hooks.yaml",
    ]
    rules: list[Rule] = []
    sources: list[str] = []
    seen_names: set[str] = set()
    for path in candidates:
        if not path.exists():
            continue
        raw = _load_yaml(path)
        if raw is None:
            continue
        hooks = raw.get("hooks") if isinstance(raw, dict) else None
        if not isinstance(hooks, list):
            print(
            f"hooks file {path}: root must contain hooks list, skipped",
            file=sys.stderr,
        )
            continue
        sources.append(str(path))
        for idx, item in enumerate(hooks):
            if not isinstance(item, dict):
                print(f"hook #{idx} in {path}: must be object, skipped", file=sys.stderr)
                continue
            rule = _compile_rule(str(path), idx, item)
            if rule is None:
                continue
            if rule.name in seen_names:
                print(f'hook "{rule.name}": duplicate name, skipped', file=sys.stderr)
                continue
            seen_names.add(rule.name)
            rules.append(rule)
    return Engine(rules, sources)


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        print(f"hooks file {path}: {exc}, skipped", file=sys.stderr)
        return None
    if not isinstance(raw, dict):
        print(f"hooks file {path}: root must be mapping, skipped", file=sys.stderr)
        return None
    return raw


def _compile_rule(source: str, idx: int, raw: dict[str, Any]) -> Rule | None:
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        print(f"hook #{idx}: name required, skipped", file=sys.stderr)
        return None
    name = name.strip()
    event_value = raw.get("event")
    event = parse_event(str(event_value or ""))
    if event is None:
        print(f'hook "{name}": unknown event "{event_value}", skipped', file=sys.stderr)
        return None
    asyncio_mode = bool(raw.get("async", False))
    if asyncio_mode and is_blocking(event):
        print(
            f'hook "{name}": async not allowed for blocking events, skipped',
            file=sys.stderr,
        )
        return None
    timeout_raw = raw.get("timeout", "30s")
    timeout = _parse_duration(str(timeout_raw))
    if timeout is None:
        print(f'hook "{name}": invalid timeout "{timeout_raw}", skipped', file=sys.stderr)
        return None
    condition = _compile_condition(name, raw.get("if"))
    if condition is _INVALID:
        return None
    action_type, action = _compile_action(name, raw.get("action"))
    if action_type is None or action is None:
        return None
    return Rule(
        name=name,
        event=event,
        condition=condition,
        action_type=action_type,
        action=action,
        only_once=bool(raw.get("only_once", False)),
        asyncio_mode=asyncio_mode,
        timeout=timeout,
        source=source,
    )


_INVALID = object()


def _compile_condition(name: str, raw: object) -> Condition | None | object:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        print(f'hook "{name}": if must be object, skipped', file=sys.stderr)
        return _INVALID
    has_all = "all_of" in raw
    has_any = "any_of" in raw
    if has_all == has_any:
        print(
            f'hook "{name}": if must contain exactly one of all_of/any_of, skipped',
            file=sys.stderr,
        )
        return _INVALID
    key = "all_of" if has_all else "any_of"
    atoms_raw = raw.get(key)
    if not isinstance(atoms_raw, list):
        print(f'hook "{name}": {key} must be list, skipped', file=sys.stderr)
        return _INVALID
    atoms: list[AtomCondition] = []
    for atom in atoms_raw:
        if not isinstance(atom, dict) or not isinstance(atom.get("field"), str):
            print(f'hook "{name}": invalid condition atom, skipped', file=sys.stderr)
            return _INVALID
        matcher = _compile_condition_matcher(name, atom.get("match"))
        if matcher is None:
            return _INVALID
        atoms.append(AtomCondition(atom["field"], matcher))
    return Condition(CombineMode(key), atoms)


def _compile_condition_matcher(name: str, raw: object):
    if not isinstance(raw, dict):
        print(f'hook "{name}": match must be object, skipped', file=sys.stderr)
        return None
    text = _match_to_pattern(raw)
    if text is None:
        print(f'hook "{name}": invalid match, skipped', file=sys.stderr)
        return None
    try:
        return compile_matcher(text, is_command=False)
    except ValueError as exc:
        print(f'hook "{name}": matcher compile failed: {exc}, skipped', file=sys.stderr)
        return None


def _match_to_pattern(raw: dict[str, Any]) -> str | None:
    typ = raw.get("type")
    if typ == "exact" and "value" in raw:
        return "=" + str(raw["value"])
    if typ == "glob" and "value" in raw:
        return str(raw["value"])
    if typ == "regex" and "value" in raw:
        return "~" + str(raw["value"])
    if typ == "not" and isinstance(raw.get("inner"), dict):
        inner = _match_to_pattern(raw["inner"])
        return None if inner is None else "!" + inner
    return None


def _compile_action(name: str, raw: object):
    if not isinstance(raw, dict):
        print(f'hook "{name}": action required, skipped', file=sys.stderr)
        return None, None
    try:
        action_type = ActionType(str(raw.get("type")))
    except ValueError:
        action_type_value = raw.get("type")
        print(
            f'hook "{name}": invalid action.type "{action_type_value}", skipped',
            file=sys.stderr,
        )
        return None, None
    if action_type == ActionType.SHELL:
        command = raw.get("command")
        if not isinstance(command, str) or not command:
            print(f'hook "{name}": shell.command required, skipped', file=sys.stderr)
            return None, None
        return action_type, ShellAction(command)
    if action_type == ActionType.PROMPT:
        text = raw.get("text")
        if not isinstance(text, str):
            print(f'hook "{name}": prompt.text required, skipped', file=sys.stderr)
            return None, None
        return action_type, PromptAction(text)
    if action_type == ActionType.HTTP:
        url = raw.get("url")
        if not isinstance(url, str) or not url:
            print(f'hook "{name}": http.url required, skipped', file=sys.stderr)
            return None, None
        headers = raw.get("headers") if isinstance(raw.get("headers"), dict) else {}
        return action_type, HttpAction(
            url=url,
            method=str(raw.get("method") or "POST"),
            headers={str(k): str(v) for k, v in headers.items()},
            body=raw.get("body") if isinstance(raw.get("body"), str) else None,
        )
    agent_name = raw.get("agent_name")
    prompt = raw.get("prompt")
    if not isinstance(agent_name, str) or not isinstance(prompt, str):
        print(f'hook "{name}": subagent.agent_name and subagent.prompt required, skipped', file=sys.stderr)
        return None, None
    return action_type, SubagentAction(agent_name, prompt)


def _parse_duration(value: str) -> float | None:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([smh]?)", value.strip())
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 3600
    return amount
