"""记忆管理器。"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import fields
from pathlib import Path
from typing import Callable

from cowcode.memory.prompts import MEMORY_UPDATE_SYSTEM_PROMPT
from cowcode.memory.store import Store
from cowcode.memory.types import UpdateAction
from cowcode.provider import Provider, Request, SystemPrompt
from cowcode.session import Message

_LOG = logging.getLogger(__name__)
_MAX_MEMORY_BYTES = 25 * 1024
_MAX_FULL_TEXT_BYTES = 12 * 1024


class Manager:
    def __init__(
        self,
        project_dir: str,
        user_dir: str,
        provider: Provider | None,
        model: str,
        on_updated: Callable[..., None] | None = None,
    ) -> None:
        self.project_store = Store(project_dir)
        self.user_store = Store(user_dir)
        self._provider = provider
        self._model = model
        self._on_updated = on_updated
        self._lock = asyncio.Lock()

    def load_index(self) -> str:
        """加载长期记忆文本：索引 + 关键记忆全文。"""

        parts: list[str] = []
        project = self.project_store.load_index().strip()
        user = self.user_store.load_index().strip()
        if project:
            parts.append("# Project memory index\n" + project)
        if user:
            parts.append("# User memory index\n" + user)
        full_text = self._load_key_memory_full_text().strip()
        if full_text:
            parts.append(full_text)
        text = "\n\n".join(parts)
        data = text.encode("utf-8")
        if len(data) <= _MAX_MEMORY_BYTES:
            return text
        return (
            data[:_MAX_MEMORY_BYTES].decode("utf-8", errors="ignore")
            + "\n(index truncated)"
        )

    def list_files(self) -> tuple[list[str], list[str]]:
        """列出项目层与用户层已加载记忆文件名。"""

        return _list_md_files(self.project_store._dir), _list_md_files(
            self.user_store._dir
        )

    def set_provider(self, provider: Provider, model: str) -> None:
        self._provider = provider
        self._model = model

    def set_on_updated(self, on_updated: Callable[..., None] | None) -> None:
        self._on_updated = on_updated

    async def update_async(self, recent_msgs: list[Message]) -> None:
        provider = self._provider
        if provider is None:
            return
        async with self._lock:
            try:
                prompt = self._build_prompt(recent_msgs)
                request = Request(
                    messages=[Message(role="user", content=prompt)],
                    tools=[],
                    system=SystemPrompt(stable=MEMORY_UPDATE_SYSTEM_PROMPT),
                )
                text = ""
                async for event in provider.stream(request):
                    if event.err is not None:
                        raise event.err
                    text += event.text
                actions = _parse_actions(text)
                project_actions = [a for a in actions if a.level == "project"]
                user_actions = [a for a in actions if a.level == "user"]
                changed_files: list[str] = []
                if project_actions:
                    changed_files.extend(
                        self.project_store.apply(project_actions).changed_files
                    )
                if user_actions:
                    changed_files.extend(
                        self.user_store.apply(user_actions).changed_files
                    )
                if changed_files and self._on_updated is not None:
                    try:
                        self._on_updated(self.load_index(), changed_files)
                    except TypeError:
                        self._on_updated(self.load_index())
                    except Exception:
                        _LOG.exception("记忆刷新回调失败")
            except Exception:
                _LOG.exception("记忆更新失败")

    def _build_prompt(self, recent_msgs: list[Message]) -> str:
        payload = [
            {
                "role": msg.role,
                "content": msg.content,
                "tool_calls": [vars(call) for call in msg.tool_calls],
                "tool_results": [vars(result) for result in msg.tool_results],
            }
            for msg in recent_msgs
        ]
        return (
            "现有记忆：\n"
            + (self.load_index() or "(empty)")
            + "\n\n最近对话：\n"
            + json.dumps(payload, ensure_ascii=False)
        )

    def _load_key_memory_full_text(self) -> str:
        sections: list[str] = []
        remaining = _MAX_FULL_TEXT_BYTES
        groups = [
            ("User profile", self.user_store, {"user"}, 4),
            ("User feedback", self.user_store, {"feedback"}, 4),
            ("Project memory", self.project_store, {"project"}, 4),
            ("Reference memory", self.project_store, {"reference"}, 2),
        ]
        for title, store, types, limit in groups:
            if remaining <= 0:
                break
            notes = store.load_full_texts(types=types, limit=limit, max_bytes=remaining)
            if not notes:
                continue
            lines = [f"# {title} full text"]
            for note in notes:
                body = note.content.strip()
                remaining -= len(body.encode("utf-8"))
                lines.append(f"## {note.title} ({note.filename})\n{body}")
            sections.append("\n\n".join(lines))
        return "\n\n".join(sections)


def _list_md_files(path: Path) -> list[str]:
    try:
        if not path.is_dir():
            return []
        return sorted(
            child.name
            for child in path.iterdir()
            if child.is_file() and child.suffix == ".md" and child.name != "MEMORY.md"
        )
    except OSError as exc:
        _LOG.warning("列出记忆文件失败 %s: %s", path, exc)
        return []


def _parse_actions(text: str) -> list[UpdateAction]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    data = json.loads(raw or "[]")
    if not isinstance(data, list):
        return []
    allowed = {field.name for field in fields(UpdateAction)}
    actions: list[UpdateAction] = []
    for item in data:
        if isinstance(item, dict):
            actions.append(
                UpdateAction(**{k: v for k, v in item.items() if k in allowed})
            )
    return actions
