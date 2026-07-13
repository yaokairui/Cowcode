"""加载 COWCODE.md 及其 @include 引用。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_INCLUDE_RE = re.compile(r"^@include\s+(.+)$")


@dataclass
class Loader:
    project_root: str
    user_home: str | None = None
    max_depth: int = 5

    def __post_init__(self) -> None:
        if self.user_home is None:
            self.user_home = os.path.expanduser("~")

    def load(self) -> str:
        root = Path(self.project_root).resolve()
        user_root = Path(self.user_home or "~").expanduser().resolve() / ".cowcode"
        candidates = [
            (root / "COWCODE.md", root),
            (root / ".cowcode" / "COWCODE.md", root),
            (user_root / "COWCODE.md", user_root),
        ]
        parts: list[str] = []
        for path, boundary in candidates:
            text = self._load_file(str(path), str(boundary), 1, set())
            if text.strip():
                parts.append(text.strip())
        return "\n\n".join(parts)

    def _load_file(
        self,
        path: str,
        boundary: str,
        depth: int,
        visited: set[str],
    ) -> str:
        raw_path = path
        real_path = Path(path).resolve()
        boundary_path = Path(boundary).resolve()
        if depth > self.max_depth:
            return f"<!-- @include 超过最大嵌套深度，已跳过: {raw_path} -->"
        if str(real_path) in visited:
            return f"<!-- @include 检测到环路，已跳过: {raw_path} -->"
        try:
            real_path.relative_to(boundary_path)
        except ValueError:
            return f"<!-- @include 路径超出允许范围，已跳过: {raw_path} -->"
        if not real_path.exists():
            return ""
        try:
            data = real_path.read_bytes()
        except OSError:
            return ""
        if b"\x00" in data[:512]:
            return f"<!-- @include 二进制文件，已跳过: {raw_path} -->"

        text = data.decode("utf-8", errors="replace")
        next_visited = set(visited)
        next_visited.add(str(real_path))
        lines: list[str] = []
        for line in text.splitlines():
            match = _INCLUDE_RE.match(line.strip())
            if match is None:
                lines.append(line)
                continue
            include_path = (real_path.parent / match.group(1).strip()).resolve()
            lines.append(
                self._load_file(
                    str(include_path),
                    str(boundary_path),
                    depth + 1,
                    next_visited,
                )
            )
        return "\n".join(lines)
