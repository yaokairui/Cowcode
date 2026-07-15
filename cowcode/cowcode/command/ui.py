"""命令 handler 使用的 UI 协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from cowcode.permission import Mode
from cowcode.session import Message

if TYPE_CHECKING:
    from cowcode.hook.rule import Rule


@dataclass(frozen=True, slots=True)
class SkillSummary:
    name: str
    description: str
    source: str = ""
    mode: str = ""


@dataclass(frozen=True, slots=True)
class WorktreeSummary:
    name: str
    path: str
    branch: str
    active: bool
    manual: bool


class WorktreeAccessor(Protocol):
    async def create(self, name: str) -> tuple[str, str]: ...
    def list(self) -> list[WorktreeSummary]: ...
    async def enter(self, name: str) -> None: ...
    async def exit(self, action: str, discard: bool) -> bool: ...
    async def remove(self, name: str, discard: bool) -> None: ...


class UI(Protocol):
    def println(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...
    def mode(self) -> Mode: ...
    def set_mode(self, mode: Mode) -> None: ...
    def inject_and_send(self, display_label: str, preset_prompt: str) -> None: ...
    def usage_in(self) -> int: ...
    def usage_out(self) -> int: ...
    def model_name(self) -> str: ...
    def cwd(self) -> str: ...
    def tool_count(self) -> int: ...
    def memory_files(self) -> list[str]: ...
    def session_path(self) -> str: ...
    def session_id(self) -> str: ...
    def quit(self) -> None: ...
    def force_compact(self) -> None: ...
    def open_resume_menu(self) -> None: ...
    async def clear_and_new_session(self) -> None: ...
    def idle(self) -> bool: ...
    def list_catalog_skills(self) -> list[SkillSummary]: ...
    def list_active_skills(self) -> list[str]: ...
    def clear_active_skills(self) -> None: ...
    def worktree_accessor(self) -> WorktreeAccessor | None: ...
    def hook_sources(self) -> list[str]: ...
    def hook_rules(self) -> list["Rule"]: ...
    async def append_assistant_message(self, text: str) -> None: ...
    def recent_messages(self, n: int) -> list[Message]: ...
    def all_messages(self) -> list[Message]: ...


class NopUI:
    """用于命令单测的空 UI。"""

    def println(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass

    def mode(self) -> Mode:
        return Mode.DEFAULT

    def set_mode(self, mode: Mode) -> None:
        pass

    def inject_and_send(self, display_label: str, preset_prompt: str) -> None:
        pass

    def usage_in(self) -> int:
        return 0

    def usage_out(self) -> int:
        return 0

    def model_name(self) -> str:
        return ""

    def cwd(self) -> str:
        return ""

    def tool_count(self) -> int:
        return 0

    def memory_files(self) -> list[str]:
        return []

    def session_path(self) -> str:
        return ""

    def session_id(self) -> str:
        return ""

    def quit(self) -> None:
        pass

    def force_compact(self) -> None:
        pass

    def open_resume_menu(self) -> None:
        pass

    async def clear_and_new_session(self) -> None:
        pass

    def idle(self) -> bool:
        return True

    def list_catalog_skills(self) -> list[SkillSummary]:
        return []

    def list_active_skills(self) -> list[str]:
        return []

    def clear_active_skills(self) -> None:
        pass

    def worktree_accessor(self) -> WorktreeAccessor | None:
        return None

    def hook_sources(self) -> list[str]:
        return []

    def hook_rules(self) -> list["Rule"]:
        return []

    async def append_assistant_message(self, text: str) -> None:
        pass

    def recent_messages(self, n: int) -> list[Message]:
        return []

    def all_messages(self) -> list[Message]:
        return []
