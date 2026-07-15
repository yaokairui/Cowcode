"""Hook 条件求值。"""

from __future__ import annotations

import json

from cowcode.hook.rule import CombineMode, Condition, Payload


def get_by_path(payload: Payload, path: str) -> str:
    """按点号路径读取 payload，缺失返回空串。"""

    current: object = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return ""
        current = current.get(part)
        if current is None:
            return ""
    if isinstance(current, str):
        return current
    if isinstance(current, bool | int | float):
        return str(current)
    return json.dumps(current, sort_keys=True)


def eval_condition(condition: Condition | None, payload: Payload) -> bool:
    if condition is None:
        return True
    checks = [
        atom.matcher.match(get_by_path(payload, atom.field)) for atom in condition.atoms
    ]
    if condition.mode == CombineMode.ALL_OF:
        return all(checks)
    if condition.mode == CombineMode.ANY_OF:
        return any(checks)
    return False
