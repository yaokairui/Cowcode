"""上下文管理状态对象。"""

from __future__ import annotations

import copy
import logging
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cowcode.compact.const import MAX_CONSECUTIVE_AUTO_COMPACT_FAILURES

_LOG = logging.getLogger(__name__)


@dataclass
class SessionContext:
    """单进程会话的落盘上下文。"""

    session_id: str
    session_dir: str
    spill_dir: str


def _new_session_id() -> str:
    try:
        suffix = secrets.token_hex(2)
    except Exception as exc:
        _LOG.warning("生成会话随机串失败，使用时间兜底: %s", exc)
        suffix = f"{datetime.now().microsecond & 0xFFFF:04x}"
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{suffix}"


def parse_session_time(session_id: str) -> datetime:
    """从新格式 session ID 解析本地时间。"""

    return datetime.strptime(session_id[:15], "%Y%m%d-%H%M%S")


def new_session_context(workspace: str) -> SessionContext:
    """创建会话目录并返回上下文。"""

    session_id = _new_session_id()
    session_dir = Path(workspace) / ".cowcode" / "sessions" / session_id
    spill_dir = session_dir / "tool-results"
    spill_dir.mkdir(parents=True, exist_ok=True)
    return SessionContext(
        session_id=session_id,
        session_dir=str(session_dir),
        spill_dir=str(spill_dir),
    )


def open_session_context(workspace: str, session_id: str) -> SessionContext:
    """打开已有会话目录并返回上下文。"""

    session_dir = Path(workspace) / ".cowcode" / "sessions" / session_id
    if not session_dir.is_dir():
        raise FileNotFoundError(str(session_dir))
    spill_dir = session_dir / "tool-results"
    return SessionContext(
        session_id=session_id,
        session_dir=str(session_dir),
        spill_dir=str(spill_dir),
    )


class ContentReplacementState:
    """工具结果替换决策账本。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._seen_ids: set[str] = set()
        self._replacements: dict[str, str] = {}

    def is_seen(self, tool_use_id: str) -> bool:
        with self._lock:
            return tool_use_id in self._seen_ids

    def decide_once(
        self,
        tool_use_id: str,
        original: str,
        decide: Callable[[], tuple[str, str]],
    ) -> str:
        """持锁完成查账本、决策、写账本。"""

        with self._lock:
            if tool_use_id in self._seen_ids:
                return self._replacements.get(tool_use_id, original)
            decision, preview = decide()
            if decision == "skip":
                return original
            if decision == "replaced":
                self._seen_ids.add(tool_use_id)
                self._replacements[tool_use_id] = preview
                return preview
            self._seen_ids.add(tool_use_id)
            return original


class AutoCompactTrackingState:
    """自动摘要失败熔断器。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._consecutive_failures = 0

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1

    def tripped(self) -> bool:
        with self._lock:
            return self._consecutive_failures >= MAX_CONSECUTIVE_AUTO_COMPACT_FAILURES


@dataclass
class FileReadRecord:
    """最近读过的文件快照。"""

    path: str
    content: str
    timestamp: datetime


class RecoveryState:
    """压缩后恢复段使用的文件追踪状态。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._files: dict[str, FileReadRecord] = {}

    def record_file(self, path: str, content: str) -> None:
        abs_path = str(Path(path).resolve())
        with self._lock:
            self._files[abs_path] = FileReadRecord(
                path=abs_path,
                content=content,
                timestamp=datetime.now(),
            )

    def snapshot(self) -> list[FileReadRecord]:
        with self._lock:
            records = [copy.copy(rec) for rec in self._files.values()]
        return sorted(records, key=lambda rec: rec.timestamp, reverse=True)
