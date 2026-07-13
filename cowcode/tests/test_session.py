"""ch09 会话存档测试。"""

from __future__ import annotations

import json
from datetime import timedelta

from cowcode.session import (
    Message,
    ToolResult,
    Writer,
    clean_expired,
    last_message_ts,
    list_sessions,
    load_session,
)


def test_writer_append_and_read(tmp_path) -> None:
    writer = Writer(str(tmp_path))
    writer.append(Message(role="user", content="hello"), "model-x", True)
    writer.append(Message(role="assistant", content="hi"), "model-x", False)
    writer.append(Message(role="tool", tool_results=[ToolResult("c1", "ok")]))
    writer.close()

    rows = [
        json.loads(line)
        for line in (tmp_path / "conversation.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert rows[0]["model"] == "model-x"
    assert [row["role"] for row in rows] == ["user", "assistant", "tool"]


def test_writer_compact_marker_and_load(tmp_path) -> None:
    writer = Writer(str(tmp_path))
    writer.append(Message(role="user", content="old"))
    writer.write_compact_marker()
    writer.append(Message(role="user", content="new"))
    writer.close()

    assert [(msg.role, msg.content) for msg in load_session(str(tmp_path))] == [
        ("user", "new")
    ]


def test_load_session_bad_line_skip_and_orphaned_tool_calls(tmp_path) -> None:
    path = tmp_path / "conversation.jsonl"
    path.write_text(
        '{"role":"user","content":"ok"}\n{invalid json\n'
        '{"role":"assistant","tool_calls":[{"id":"c1","name":"read_file","input":"{}"}]}\n',
        encoding="utf-8",
    )
    assert [(msg.role, msg.content) for msg in load_session(str(tmp_path))] == [
        ("user", "ok")
    ]


def test_last_message_ts_skips_bad_lines_and_markers(tmp_path) -> None:
    path = tmp_path / "conversation.jsonl"
    path.write_text(
        '{"role":"user","content":"old","ts":10}\n'
        "{invalid json\n"
        '{"type":"compact","ts":20}\n'
        '{"role":"assistant","content":"new","ts":30}\n',
        encoding="utf-8",
    )
    assert last_message_ts(str(tmp_path)) == 30


def test_last_message_ts_missing_or_empty(tmp_path) -> None:
    assert last_message_ts(str(tmp_path)) is None
    (tmp_path / "conversation.jsonl").write_text(
        '{"type":"compact","ts":20}\n', encoding="utf-8"
    )
    assert last_message_ts(str(tmp_path)) is None


def test_list_sessions_filters_legacy_and_clean_expired(tmp_path) -> None:
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    old = sessions / "20200101-000000-abcd"
    new = sessions / "20990101-000000-abcd"
    legacy = sessions / "1717000000-abc12345"
    for path in (old, new, legacy):
        path.mkdir()
        (path / "conversation.jsonl").write_text(
            '{"role":"user","content":"hello","model":"m"}\n', encoding="utf-8"
        )

    items = list_sessions(str(sessions))
    assert [item.id for item in items] == [
        "20990101-000000-abcd",
        "20200101-000000-abcd",
    ]
    clean_expired(str(sessions), timedelta(days=30))
    assert not old.exists()
    assert new.exists()
    assert legacy.exists()
