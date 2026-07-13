"""记忆文件存储。"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from cowcode.memory.types import UpdateAction

_TYPE_ALIASES = {
    "user_preference": "user",
    "correction_feedback": "feedback",
    "project_knowledge": "project",
    "reference_material": "reference",
}
_VALID_TYPES = {"user", "feedback", "project", "reference"}

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


@dataclass
class ApplyResult:
    changed_files: list[str]


@dataclass
class MemoryFullText:
    filename: str
    type: str
    title: str
    content: str


class Store:
    def __init__(self, dir: str) -> None:
        self._dir = Path(dir)
        self._lock = threading.Lock()

    def ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def load_index(self) -> str:
        path = self._dir / "MEMORY.md"
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def apply(self, actions: list[UpdateAction]) -> ApplyResult:
        changed_files: list[str] = []
        with self._lock:
            self.ensure_dir()
            for action in actions:
                changed: str | None = None
                if action.action == "create":
                    changed = self._create(action)
                elif action.action == "update":
                    changed = self._update(action)
                elif action.action == "delete":
                    changed = self._delete(action)
                if changed:
                    changed_files.append(changed)
        return ApplyResult(changed_files)

    def _create(self, action: UpdateAction) -> str:
        note_type = _normalize_type(action.type or "project")
        slug = _safe_slug(action.slug or action.title or "note")
        filename = action.filename or f"{slug}.md"
        now = _now()
        self._write_note(
            filename, note_type, action.title or slug, action.content, now, now
        )
        self._upsert_index(
            filename,
            note_type,
            action.title or slug,
            action.summary or _summary(action.content),
        )
        return filename

    def _update(self, action: UpdateAction) -> str | None:
        if not action.filename:
            return None
        path = self._dir / action.filename
        old_meta = _read_meta(path)
        now = _now()
        note_type = _normalize_type(
            action.type or str(old_meta.get("type") or "project")
        )
        title = action.title or str(old_meta.get("title") or action.filename)
        created = str(old_meta.get("created") or now)
        self._write_note(
            action.filename, note_type, title, action.content, created, now
        )
        self._upsert_index(
            action.filename,
            note_type,
            title,
            action.summary or _summary(action.content),
        )
        return action.filename

    def _delete(self, action: UpdateAction) -> str | None:
        if not action.filename:
            return None
        try:
            (self._dir / action.filename).unlink()
        except FileNotFoundError:
            pass
        self._remove_index(action.filename)
        return action.filename

    def _write_note(
        self,
        filename: str,
        note_type: str,
        title: str,
        content: str,
        created: str,
        updated: str,
    ) -> None:
        meta = {"name": Path(filename).stem, "description": title, "type": note_type}
        body = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip()
        (self._dir / filename).write_text(
            f"---\n{body}\n---\n\n{content.strip()}\n",
            encoding="utf-8",
        )

    def _upsert_index(
        self, filename: str, note_type: str, title: str, summary: str
    ) -> None:
        path = self._dir / "MEMORY.md"
        marker = f"({filename})"
        line = f"- [{title}]({filename}) — {summary}"
        lines = [ln for ln in self.load_index().splitlines() if marker not in ln]
        lines.append(line)
        path.write_text("\n".join(lines[-200:]) + "\n", encoding="utf-8")

    def _remove_index(self, filename: str) -> None:
        path = self._dir / "MEMORY.md"
        marker = f"({filename})"
        lines = [ln for ln in self.load_index().splitlines() if marker not in ln]
        path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")

    def _remove_index(self, filename: str) -> None:
        path = self._dir / "MEMORY.md"
        marker = f"({filename})"
        lines = [ln for ln in self.load_index().splitlines() if marker not in ln]
        path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")

    def load_full_texts(
        self,
        types: set[str] | None = None,
        limit: int = 4,
        max_bytes: int = 12 * 1024,
    ) -> list[MemoryFullText]:
        """读取关键记忆全文，损坏文件自动跳过。"""

        if not self._dir.is_dir() or limit <= 0 or max_bytes <= 0:
            return []
        items: list[MemoryFullText] = []
        used = 0
        for path in sorted(self._dir.glob("*.md")):
            if path.name == "MEMORY.md":
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError:
                continue
            parsed = _parse_note(raw)
            if parsed is None:
                continue
            note_type, title, content = parsed
            if types is not None and note_type not in types:
                continue
            encoded_len = len(content.encode("utf-8"))
            if used + encoded_len > max_bytes:
                break
            used += encoded_len
            items.append(MemoryFullText(path.name, note_type, title, content))
            if len(items) >= limit:
                break
        return items


def _normalize_type(value: str) -> str:
    note_type = _TYPE_ALIASES.get(value, value)
    return note_type if note_type in _VALID_TYPES else "project"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def _safe_slug(value: str) -> str:
    slug = value.strip().lower().replace("-", "_").replace(" ", "_")
    slug = _SLUG_RE.sub("_", slug).strip("_")
    return slug or "note"


def _summary(content: str) -> str:
    text = " ".join(content.strip().split())
    return text[:80] if text else "updated memory"


def _parse_note(text: str) -> tuple[str, str, str] | None:
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    data = yaml.safe_load(parts[1]) or {}
    if not isinstance(data, dict):
        return None
    note_type = _normalize_type(str(data.get("type") or "project"))
    title = str(
        data.get("description") or data.get("title") or data.get("name") or "Memory"
    )
    content = parts[2].strip()
    if not content:
        return None
    return note_type, title, content


def _parse_note(text: str) -> tuple[str, str, str] | None:
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    data = yaml.safe_load(parts[1]) or {}
    if not isinstance(data, dict):
        return None
    note_type = _normalize_type(str(data.get("type") or "project"))
    title = str(
        data.get("description") or data.get("title") or data.get("name") or "Memory"
    )
    content = parts[2].strip()
    if not content:
        return None
    return note_type, title, content


def _read_meta(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    data = yaml.safe_load(parts[1]) or {}
    return data if isinstance(data, dict) else {}
