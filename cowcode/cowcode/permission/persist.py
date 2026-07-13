"""本地层规则持久化。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from cowcode.permission import Engine
from cowcode.permission.settings import SettingsError, load_settings


def persist_local_allow(engine: Engine, call: Any) -> None:
    """把一条精确 allow 规则写入本地层配置文件，同步内存。"""
    rule_str = _rule_for(call)
    if not rule_str:
        return

    # 加载现有 local 配置
    local_path = engine.local_path
    if not local_path:
        return
    try:
        settings = load_settings(local_path)
    except SettingsError:
        settings = __import__(
            "cowcode.permission.settings", fromlist=["Settings"]
        ).Settings()

    # 去重追加
    if rule_str not in settings.permissions.allow:
        settings.permissions.allow.append(rule_str)

    # 写文件
    try:
        parent = Path(local_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "permissions": {
                "allow": settings.permissions.allow,
                "deny": settings.permissions.deny,
            },
        }
        if settings.default_mode:
            payload["default_mode"] = settings.default_mode
        yaml.safe_dump(
            payload,
            Path(local_path).open("w", encoding="utf-8"),
            allow_unicode=True,
            default_flow_style=False,
        )
    except OSError:
        return  # 写失败不阻断执行

    # 同步内存
    from cowcode.permission import _parse_rule

    rule_obj, ok = _parse_rule(rule_str)
    if ok and rule_obj.tool:
        engine.local.allow.append(rule_obj)


def _rule_for(call: Any) -> str:
    """为一次工具调用生成精确规则文本。"""
    from cowcode.permission import _extract_target, _friendly_name

    name = getattr(call, "name", "") or ""
    friendly = _friendly_name(name)
    target, is_file, ok = _extract_target(call)
    if not ok:
        return ""
    if not target:
        return friendly
    # bash 命令：精确匹配
    escaped = _escape_glob_meta(target)
    return f"{friendly}({escaped})"


def _escape_glob_meta(text: str) -> str:
    """对 glob 元字符加中括号转义，防止规则被泛化。"""
    result = []
    for ch in text:
        if ch in ("*", "?", "[", "]"):
            result.append(f"[{ch}]")
        else:
            result.append(ch)
    return "".join(result)
