from __future__ import annotations

import re

import pytest

from cowcode.team import BackendType, Manager, TeammateInfo
from cowcode.team.persistence import atomic_write_json, sanitize
from cowcode.team.registry import AgentNameRegistry


@pytest.mark.asyncio
async def test_sanitize_and_manager_create(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cowcode.team.manager.detect", lambda: BackendType.IN_PROCESS)
    reg = AgentNameRegistry()
    mgr = Manager(tmp_path, tmp_path, None, None, reg)

    assert sanitize("foo bar/baz") == "foo-bar-baz"

    team = await mgr.create("foo bar/baz", "desc")
    assert team.sanitized_name == "foo-bar-baz"
    assert (tmp_path / ".cowcode" / "teams" / "foo-bar-baz" / "config.json").exists()
    assert reg.resolve("lead") == "lead"


@pytest.mark.asyncio
async def test_manager_duplicate_suffix_and_reload(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("cowcode.team.manager.detect", lambda: BackendType.IN_PROCESS)
    mgr = Manager(tmp_path, tmp_path, None, None, AgentNameRegistry())
    first = await mgr.create("demo", "")
    second = await mgr.create("demo", "")
    assert first.sanitized_name == "demo"
    assert second.sanitized_name == "demo-2"

    # 模拟另一个进程先把 alice 写到磁盘,当前内存随后 set_active 也不能丢更新。
    data = first.to_dict()
    data["members"].append(
        TeammateInfo(name="alice", agent_id="agent-123", is_active=True).to_dict()
    )
    atomic_write_json(first.config_path, data)
    await first.set_member_active("alice", False)
    reloaded = Manager(tmp_path, tmp_path, None, None, AgentNameRegistry()).get("demo")
    assert reloaded is not None
    alice = reloaded.member_by_name("alice")
    assert alice is not None
    assert alice.is_active is False


def test_task_id_shape_from_task_manager() -> None:
    from cowcode.task_manager import Manager as TaskManager

    assert re.fullmatch(r"task_[0-9a-f]{6}", TaskManager._next_id())
