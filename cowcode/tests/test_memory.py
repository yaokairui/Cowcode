"""ch09 记忆系统测试。"""

from __future__ import annotations

from typing import AsyncIterator

import pytest

from cowcode.memory import Manager, Store, UpdateAction
from cowcode.provider import Request
from cowcode.session import Message, StreamEvent


def test_store_create_update_delete(tmp_path) -> None:
    store = Store(str(tmp_path))
    result = store.apply(
        [
            UpdateAction(
                action="create",
                level="project",
                type="project",
                title="Use Chinese",
                slug="use_chinese",
                content="项目默认中文回复。",
            )
        ]
    )
    note = tmp_path / "use_chinese.md"
    assert result.changed_files == ["use_chinese.md"]
    assert note.exists()
    assert "Use Chinese" in (tmp_path / "MEMORY.md").read_text(encoding="utf-8")

    result = store.apply(
        [
            UpdateAction(
                action="update",
                level="project",
                filename=note.name,
                title="Use Chinese",
                content="更新内容",
            )
        ]
    )
    assert result.changed_files == ["use_chinese.md"]
    assert "更新内容" in note.read_text(encoding="utf-8")

    result = store.apply(
        [UpdateAction(action="delete", level="project", filename=note.name)]
    )
    assert result.changed_files == ["use_chinese.md"]
    assert not note.exists()
    assert "Use Chinese" not in (tmp_path / "MEMORY.md").read_text(encoding="utf-8")


def test_store_load_full_texts(tmp_path) -> None:
    store = Store(str(tmp_path))
    store.apply(
        [
            UpdateAction(
                action="create",
                level="user",
                type="user",
                title="User Role",
                slug="user_role",
                content="用户是 Go 工程师。",
            ),
            UpdateAction(
                action="create",
                level="user",
                type="project",
                title="Project Rule",
                slug="project_rule",
                content="项目使用 Python。",
            ),
        ]
    )
    notes = store.load_full_texts(types={"user"})
    assert len(notes) == 1
    assert notes[0].filename == "user_role.md"
    assert "Go 工程师" in notes[0].content


def test_manager_load_index_and_truncate(tmp_path) -> None:
    project = tmp_path / "project"
    user = tmp_path / "user"
    project.mkdir()
    user.mkdir()
    (project / "MEMORY.md").write_text("p", encoding="utf-8")
    (user / "MEMORY.md").write_text("u", encoding="utf-8")
    manager = Manager(str(project), str(user), None, "")
    assert manager.load_index().startswith("# Project memory index\np")

    (project / "MEMORY.md").write_text("x" * (26 * 1024), encoding="utf-8")
    assert manager.load_index().endswith("(index truncated)")


def test_manager_load_index_includes_key_full_text(tmp_path) -> None:
    project = tmp_path / "project"
    user = tmp_path / "user"
    manager = Manager(str(project), str(user), None, "")
    manager.user_store.apply(
        [
            UpdateAction(
                action="create",
                level="user",
                type="user",
                title="User Role",
                slug="user_role",
                content="用户是 Go 工程师。",
            )
        ]
    )
    text = manager.load_index()
    assert "# User profile full text" in text
    assert "用户是 Go 工程师" in text


def test_manager_list_files(tmp_path) -> None:
    missing_project = tmp_path / "missing-project"
    missing_user = tmp_path / "missing-user"
    manager = Manager(str(missing_project), str(missing_user), None, "")
    assert manager.list_files() == ([], [])

    project = tmp_path / "project"
    user = tmp_path / "user"
    project.mkdir()
    user.mkdir()
    (project / "MEMORY.md").write_text("p", encoding="utf-8")
    (project / "b.md").write_text("b", encoding="utf-8")
    (project / "a.md").write_text("a", encoding="utf-8")
    (project / "skip.txt").write_text("x", encoding="utf-8")
    (user / "MEMORY.md").write_text("u", encoding="utf-8")

    manager = Manager(str(project), str(user), None, "")
    assert manager.list_files() == (["a.md", "b.md"], [])


class FakeProvider:
    @property
    def model(self) -> str:
        return "fake"

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        assert request.tools == []
        yield StreamEvent(
            text='[{"action":"create","level":"project","type":"project","title":"Rule","slug":"rule","content":"body"}]'
        )
        yield StreamEvent(done=True)


@pytest.mark.asyncio
async def test_manager_update_async_parses_response(tmp_path) -> None:
    manager = Manager(
        str(tmp_path / "project"), str(tmp_path / "user"), FakeProvider(), "fake"
    )
    await manager.update_async(
        [
            Message(role="user", content="记住项目规则"),
            Message(role="assistant", content="好"),
        ]
    )
    assert (tmp_path / "project" / "rule.md").exists()


@pytest.mark.asyncio
async def test_manager_update_async_calls_on_updated(tmp_path) -> None:
    updates: list[tuple[str, list[str]]] = []
    manager = Manager(
        str(tmp_path / "project"),
        str(tmp_path / "user"),
        FakeProvider(),
        "fake",
        on_updated=lambda memory, files: updates.append((memory, files)),
    )
    await manager.update_async(
        [
            Message(role="user", content="记住项目规则"),
            Message(role="assistant", content="好"),
        ]
    )
    assert len(updates) == 1
    assert "Rule" in updates[0][0]
    assert updates[0][1] == ["rule.md"]


class EmptyProvider:
    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(text="[]")
        yield StreamEvent(done=True)


@pytest.mark.asyncio
async def test_manager_update_async_skips_callback_for_empty_actions(tmp_path) -> None:
    updates: list[str] = []
    manager = Manager(
        str(tmp_path / "project"),
        str(tmp_path / "user"),
        EmptyProvider(),
        "fake",
        on_updated=updates.append,
    )
    await manager.update_async([Message(role="user", content="hello")])
    assert updates == []
