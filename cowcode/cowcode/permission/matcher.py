"""权限规则匹配器。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Protocol


class Matcher(Protocol):
    """规则匹配统一接口。"""

    def match(self, s: str) -> bool:
        """判断输入是否命中规则。"""
        ...

    def __str__(self) -> str:
        """返回可读规则文本。"""
        ...


@dataclass(frozen=True)
class ExactMatcher:
    """整串精确匹配。"""

    value: str

    def match(self, s: str) -> bool:
        return s == self.value

    def __str__(self) -> str:
        return f"={self.value}"


@dataclass(frozen=True)
class GlobMatcher:
    """glob 匹配；命令串与路径使用不同语义。"""

    pattern: str
    is_command: bool

    def match(self, s: str) -> bool:
        if self.is_command:
            return match_command(self.pattern, s)
        return match_path(self.pattern, s)

    def __str__(self) -> str:
        return self.pattern


@dataclass(frozen=True)
class RegexMatcher:
    """正则 search 匹配，编译发生在加载期。"""

    src: str
    compiled: re.Pattern[str]

    def match(self, s: str) -> bool:
        return self.compiled.search(s) is not None

    def __str__(self) -> str:
        return f"~{self.src}"


@dataclass(frozen=True)
class NotMatcher:
    """对内部 matcher 的结果取反。"""

    inner: Matcher

    def match(self, s: str) -> bool:
        return not self.inner.match(s)

    def __str__(self) -> str:
        return f"!{self.inner}"


def compile_matcher(pattern: str, *, is_command: bool) -> Matcher:
    """把简洁串编译为 matcher。

    前缀语义：`=` 精确，`~` 正则，`!` 取反，其它为 glob。
    """

    if pattern == "":
        raise ValueError("empty matcher pattern")
    if pattern.startswith("="):
        return ExactMatcher(pattern[1:])
    if pattern.startswith("~"):
        src = pattern[1:]
        try:
            compiled = re.compile(src)
        except re.error as exc:
            raise ValueError(str(exc)) from exc
        return RegexMatcher(src, compiled)
    if pattern.startswith("!"):
        return NotMatcher(compile_matcher(pattern[1:], is_command=is_command))
    return GlobMatcher(pattern, is_command)


def match_command(pattern: str, command: str) -> bool:
    """命令串 glob：`*` 可匹配空格。"""

    return fnmatchcase(command, pattern)


def match_path(pattern: str, target: str) -> bool:
    """路径 glob：`*` 段内匹配，`**` 跨路径段匹配。"""

    pat_segments = pattern.replace("\\", "/").split("/")
    tgt_segments = target.replace("\\", "/").split("/")
    return _segment_list_match(pat_segments, tgt_segments)


def _segment_list_match(pat_parts: list[str], tgt_parts: list[str]) -> bool:
    pi = ti = 0
    while pi < len(pat_parts) and ti < len(tgt_parts):
        part = pat_parts[pi]
        if part == "**":
            pi += 1
            if pi == len(pat_parts):
                return True
            while ti < len(tgt_parts):
                if _segment_list_match(pat_parts[pi:], tgt_parts[ti:]):
                    return True
                ti += 1
            return False
        if not fnmatchcase(tgt_parts[ti], part):
            return False
        pi += 1
        ti += 1
    while pi < len(pat_parts) and pat_parts[pi] == "**":
        pi += 1
    return pi == len(pat_parts) and ti == len(tgt_parts)
