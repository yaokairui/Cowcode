"""权限引擎——前四层判定流水线。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cowcode.permission import (
    Category,
    Decision,
    Engine,
    Mode,
    _categorize,
    _extract_target,
    _friendly_name,
)
from cowcode.permission.blacklist import hits_blacklist
from cowcode.permission.sandbox import resolve_root, sandbox_ok
from cowcode.permission.settings import SettingsError, default_rules, load_settings, to_rule_set


def new_engine(root: str) -> tuple[Engine, Exception | None]:
    """构造权限引擎。

    致命错误（仅 resolve_root 失败）也返回非 None 降级引擎 + err；
    配置加载失败仅降级跳过，不崩溃。
    """
    try:
        resolved = resolve_root(root)
    except Exception as exc:
        # 致命错：返回降级引擎
        return (
            Engine(
                root=root,
                blacklist=[],
                user=default_rules(),
                project=default_rules(),
                local=default_rules(),
                local_path="",
                start_mode=Mode.DEFAULT,
            ),
            exc,
        )

    from cowcode.permission.blacklist import _BLACKLIST

    # 加载三层配置
    home = str(Path.home())
    local_path = os.path.join(resolved, ".cowcode", "settings.local.yaml")

    user_settings = _load_or_empty(os.path.join(home, ".cowcode", "settings.yaml"))
    project_settings = _load_or_empty(os.path.join(resolved, ".cowcode", "settings.yaml"))
    local_settings = _load_or_empty(local_path)

    user_rules = to_rule_set(user_settings)
    project_rules = to_rule_set(project_settings)
    local_rules = to_rule_set(local_settings)

    # 确定启动模式（本地 > 项目 > 用户 > default）
    start_mode = Mode.DEFAULT
    for settings in (user_settings, project_settings, local_settings):
        if settings.default_mode:
            mode, ok = Mode.parse(settings.default_mode)
            if ok:
                start_mode = mode

    return (
        Engine(
            root=resolved,
            blacklist=list(_BLACKLIST),
            user=user_rules,
            project=project_rules,
            local=local_rules,
            local_path=local_path,
            start_mode=start_mode,
        ),
        None,
    )


def _load_or_empty(path: str) -> Any:
    try:
        return load_settings(path)
    except SettingsError:
        return _default_settings


_default_settings = __import__("cowcode.permission.settings", fromlist=["Settings"]).Settings()


def mode_fallback(mode: Mode, cat: Category) -> Decision:
    """F5 权限模式矩阵，只产 Allow 或 Ask。"""
    if cat == Category.READ or mode == Mode.BYPASS:
        return Decision.ALLOW
    if mode == Mode.ACCEPT_EDITS and cat == Category.WRITE:
        return Decision.ALLOW
    return Decision.ASK


def check(
    engine: Engine,
    mode: Mode,
    call: Any,
    read_only: bool,
) -> tuple[Decision, str]:
    """前四层判定流水线：黑名单→沙箱→规则→模式兜底。

    BYPASS 模式下仅过黑名单，其余全部放行。
    """
    cat = _categorize(getattr(call, "name", "") or "", read_only)
    friendly = _friendly_name(getattr(call, "name", "") or "")
    target, is_file, ok = _extract_target(call)

    # ① 黑名单（所有模式强制，包括 BYPASS）
    if cat == Category.EXEC and target and hits_blacklist(target):
        return Decision.DENY, f"命中危险命令黑名单：{target[:120]}"

    # BYPASS：跳过沙箱/规则/兜底，直接放行除黑名单外的所有操作
    if mode == Mode.BYPASS:
        return Decision.ALLOW, ""

    # ② 沙箱（仅文件类）
    if is_file:
        if not ok:
            return Decision.DENY, "无法解析文件路径参数，安全拒绝"
        if not sandbox_ok(engine.root, target):
            return Decision.DENY, f"路径在项目目录之外：{target}"

    # ③ 规则引擎（就近命中）
    for rule_set, _label in (
        (engine.local, "local"),
        (engine.project, "project"),
        (engine.user, "user"),
    ):
        decision, hit = rule_set.match(friendly, target)
        if hit:
            reason = "" if decision == Decision.ALLOW else f"匹配 deny 规则：{friendly}({target})"
            return decision, reason

    # ④ 模式兜底
    fallback = mode_fallback(mode, cat)
    if fallback == Decision.ALLOW:
        return Decision.ALLOW, ""
    return Decision.ASK, f"{mode} 模式下 {_cat_label(cat)} 类操作需确认"


# Monkey-patch check onto Engine so Agent code can call engine.check(...)
Engine.check = lambda self, mode, call, read_only: check(self, mode, call, read_only)  # type: ignore[attr-defined]


def _cat_label(cat: Category) -> str:
    return {Category.READ: "只读", Category.WRITE: "文件写", Category.EXEC: "命令执行"}.get(cat, "未知")

def start_mode(engine: Engine) -> Mode:
    return engine.start_mode
