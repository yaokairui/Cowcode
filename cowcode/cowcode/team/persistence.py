"""Team 持久化辅助。"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from cowcode.team.types import Team, TeammateInfo

_SAFE_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def sanitize(name: str) -> str:
    """把团队名转换为可用于路径的 slug。"""

    return _SAFE_RE.sub("-", name).strip("-")


def atomic_write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def attach_paths(team: Team, base_dir: str | Path) -> Team:
    config_dir = Path(base_dir) / team.sanitized_name
    team.config_dir = str(config_dir)
    team.config_path = str(config_dir / "config.json")
    team.tasks_path = str(config_dir / "tasks.json")
    team.mailbox_dir = str(config_dir / "mailbox")
    return team


async def reload_from_disk_locked(team: Team) -> None:
    """调用方已持锁；跨进程写入前先重读成员列表。"""

    try:
        data = read_json(team.config_path)
    except Exception:
        return
    if not isinstance(data, dict):
        return
    members = data.get("members")
    if not isinstance(members, list):
        return
    team.members = [
        TeammateInfo.from_dict(item) for item in members if isinstance(item, dict)
    ]
