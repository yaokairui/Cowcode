"""Cowcode permission module — five-layer defence pipeline.

Layers: ① blacklist → ② sandbox → ③ rules → ④ mode fallback → ⑤ human-in-the-loop
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


# ----- enums -----
class Mode(IntEnum):
    DEFAULT = 0
    ACCEPT_EDITS = 1
    PLAN = 2
    BYPASS = 3

    def __str__(self) -> str:
        return _MODE_STRS[self]

    @staticmethod
    def parse(s: str) -> tuple[Mode, bool]:
        """大小写不敏感识别；未知返回 (DEFAULT, False)。"""
        lower = s.strip().lower()
        for mode, label in _MODE_STRS.items():
            if label.lower() == lower:
                return mode, True
        return Mode.DEFAULT, False


_MODE_STRS = {
    Mode.DEFAULT: "default",
    Mode.ACCEPT_EDITS: "acceptEdits",
    Mode.PLAN: "plan",
    Mode.BYPASS: "bypassPermissions",
}


def next_mode(mode: Mode) -> Mode:
    """循环切换四档权限模式。"""
    return Mode((int(mode) + 1) % 4)


class Decision(IntEnum):
    ALLOW = 0
    DENY = 1
    ASK = 2


class Category(IntEnum):
    READ = 0
    WRITE = 1
    EXEC = 2


_OUTCOME_INDEXS: list[Outcome] = []  # type: ignore[assignment] # 在类定义后填充


class Outcome(IntEnum):
    DENY_ONCE = 0
    ALLOW_ONCE = 1
    ALLOW_FOREVER = 2

    @classmethod
    def for_index(cls, index: int) -> Outcome:
        """0→ALLOW_ONCE, 1→ALLOW_FOREVER, 2→DENY_ONCE。"""
        return _OUTCOME_INDEXS[index]


_OUTCOME_INDEXS[:] = [Outcome.ALLOW_ONCE, Outcome.ALLOW_FOREVER, Outcome.DENY_ONCE]


# ----- data classes -----
@dataclass
class Rule:
    tool: str  # friendly name
    pattern: str = ""  # "" means match all calls
    allow: bool = True


@dataclass
class RuleSet:
    allow: list[Rule] = field(default_factory=list)
    deny: list[Rule] = field(default_factory=list)

    def match(self, friendly: str, target: str) -> tuple[Decision, bool]:
        """先 deny 后 allow；命中返回 (Decision, True)。"""
        for rule in self.deny:
            if rule.tool == friendly and _match_pattern(rule.pattern, target):
                return Decision.DENY, True
        for rule in self.allow:
            if rule.tool == friendly and _match_pattern(rule.pattern, target):
                return Decision.ALLOW, True
        return Decision.ALLOW, False


@dataclass
class PermissionsBlock:
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)


@dataclass
class Settings:
    default_mode: str = ""
    permissions: PermissionsBlock = field(default_factory=PermissionsBlock)


@dataclass
class Engine:
    root: str
    blacklist: list[_re.Pattern]
    user: RuleSet
    project: RuleSet
    local: RuleSet
    local_path: str = ""
    start_mode: Mode = Mode.DEFAULT


class ApprovalError(Exception):
    """权限模块可恢复错误。"""


class SettingsError(Exception):
    """配置文件解析失败。"""


# ----- helpers (shared) -----
def _friendly_name(internal: str) -> str:
    _MAP = {
        "bash": "Bash",
        "read_file": "Read",
        "write_file": "Write",
        "edit_file": "Edit",
        "glob": "Glob",
        "grep": "Grep",
        "AskUserQuestion": "AskUserQuestion",
    }
    return _MAP.get(internal, internal)


def _categorize(internal: str, read_only: bool) -> Category:
    if read_only:
        return Category.READ
    if internal in ("write_file", "edit_file"):
        return Category.WRITE
    return Category.EXEC


def _match_pattern(pattern: str, target: str) -> bool:
    """pattern 为空 → 匹配全部；否则按 glob 语义匹配。"""
    if not pattern:
        return True
    return _segments_match(pattern, target)


def _segments_match(pattern: str, target: str) -> bool:
    """glob 段匹配：* 段内任意字符；** 跨任意段（仅对 / 分隔路径有意义）。"""
    import fnmatch as _fnmatch

    # 对命令串：直接用 fnmatch（* 匹配含空格的任意字符）
    if "/" not in pattern and "/" not in target:
        return _fnmatch.fnmatch(target, pattern)

    # 对文件路径：分段匹配
    pat_segments = pattern.replace("\\", "/").split("/")
    tgt_segments = target.replace("\\", "/").split("/")
    return _segment_list_match(pat_segments, tgt_segments)


def _segment_list_match(pat_parts: list[str], tgt_parts: list[str]) -> bool:
    import fnmatch as _fnmatch

    pi = ti = 0
    while pi < len(pat_parts) and ti < len(tgt_parts):
        p = pat_parts[pi]
        if p == "**":
            pi += 1
            if pi == len(pat_parts):
                return True
            for look in range(ti, len(tgt_parts)):
                if _fnmatch.fnmatch(tgt_parts[look], pat_parts[pi]):
                    ti = look
                    break
            else:
                return False
        elif not _fnmatch.fnmatch(tgt_parts[ti], p):
            return False
        pi += 1
        ti += 1
    while pi < len(pat_parts) and pat_parts[pi] == "**":
        pi += 1
    return pi == len(pat_parts) and ti == len(tgt_parts)


def _parse_rule(text: str) -> tuple[Rule, bool]:
    """解析 "Tool(pattern)" 或 "Tool"。非法返回空 Rule + False。"""
    text = text.strip()
    if not text:
        return Rule("", "", False), False
    if "(" not in text:
        return Rule(tool=text, pattern="", allow=True), True
    open_idx = text.index("(")
    if not text.endswith(")"):
        return Rule("", "", False), False
    tool = text[:open_idx].strip()
    pattern = text[open_idx + 1 : -1].strip()
    if not tool:
        return Rule("", "", False), False
    return Rule(tool=tool, pattern=pattern, allow=True), True


def _extract_target(call: Any) -> tuple[str, bool, bool]:
    """从 ToolCall.input 提取目标字符串。返回 (target, is_file, ok)。"""
    import json as _json

    raw = getattr(call, "input", "") or "{}"
    try:
        data = _json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return ("", False, False)
    if not isinstance(data, dict):
        return ("", False, False)

    name = getattr(call, "name", "") or ""

    if name in ("read_file", "write_file", "edit_file"):
        path = data.get("path")
        if not isinstance(path, str) or not path:
            return ("", True, False)
        return (path, True, True)

    if name in ("glob", "grep"):
        path = data.get("path") or "."
        if not isinstance(path, str):
            return (".", True, False)
        return (path, True, True)

    if name == "bash":
        command = data.get("command")
        if not isinstance(command, str):
            return ("", False, False)
        return (command, False, True)

    return ("", False, False)


def _check_glob_imports() -> None:
    """确保 fnmatch 可用。"""


# Re-export from submodules
from cowcode.permission.engine import check as check  # noqa: E402
from cowcode.permission.engine import mode_fallback as mode_fallback  # noqa: E402
from cowcode.permission.engine import new_engine as new_engine  # noqa: E402
from cowcode.permission.engine import start_mode as start_mode  # noqa: E402
from cowcode.permission.persist import persist_local_allow as persist_local_allow  # noqa: E402
