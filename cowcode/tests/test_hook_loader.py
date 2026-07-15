"""Hook loader 测试。"""

from __future__ import annotations

from pathlib import Path

from cowcode.hook.event import Event
from cowcode.hook.loader import load
from cowcode.hook.rule import ActionType


def _write_hooks(root: Path, text: str) -> None:
    hooks_dir = root / ".cowcode"
    hooks_dir.mkdir()
    (hooks_dir / "hooks.yaml").write_text(text, encoding="utf-8")


def test_load_valid_project_hooks(tmp_path: Path) -> None:
    _write_hooks(
        tmp_path,
        """
hooks:
  - name: start-note
    event: SessionStart
    action:
      type: prompt
      text: zh-CN
  - name: block-write
    event: PreToolUse
    if:
      all_of:
        - field: tool_name
          match: {type: exact, value: write_file}
    action:
      type: shell
      command: echo blocked
""",
    )

    engine = load(tmp_path)

    assert len(engine.rules) == 2
    assert engine.rules[0].name == "start-note"
    assert engine.rules[0].event == Event.SESSION_START
    assert engine.rules[0].action_type == ActionType.PROMPT
    assert engine.sources == [str(tmp_path / ".cowcode" / "hooks.yaml")]


def test_invalid_rules_are_skipped_but_valid_rules_load(tmp_path: Path, capsys) -> None:
    _write_hooks(
        tmp_path,
        """
hooks:
  - name: ""
    event: SessionStart
    action: {type: prompt, text: x}
  - name: bad-event
    event: UnknownEvent
    action: {type: prompt, text: x}
  - name: bad-action
    event: SessionStart
    action: {type: nope}
  - name: ok
    event: Stop
    action: {type: prompt, text: done}
""",
    )

    engine = load(tmp_path)
    err = capsys.readouterr().err

    assert [rule.name for rule in engine.rules] == ["ok"]
    assert "name required" in err
    assert 'unknown event "UnknownEvent"' in err
    assert "invalid action.type" in err


def test_all_of_and_any_of_together_is_invalid(tmp_path: Path, capsys) -> None:
    _write_hooks(
        tmp_path,
        """
hooks:
  - name: invalid-condition
    event: PreToolUse
    if:
      all_of: []
      any_of: []
    action: {type: prompt, text: x}
""",
    )

    engine = load(tmp_path)

    assert engine.rules == []
    assert "exactly one of all_of/any_of" in capsys.readouterr().err


def test_async_blocking_event_is_invalid(tmp_path: Path, capsys) -> None:
    _write_hooks(
        tmp_path,
        """
hooks:
  - name: async-blocking
    event: PreToolUse
    async: true
    action: {type: prompt, text: x}
""",
    )

    engine = load(tmp_path)

    assert engine.rules == []
    assert "async not allowed for blocking events" in capsys.readouterr().err


def test_project_and_user_hooks_merge_and_duplicate_name_skips_later(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    home.mkdir()
    _write_hooks(
        project,
        """
hooks:
  - name: same
    event: SessionStart
    action: {type: prompt, text: project}
""",
    )
    _write_hooks(
        home,
        """
hooks:
  - name: same
    event: Stop
    action: {type: prompt, text: user}
  - name: user-only
    event: Stop
    action: {type: prompt, text: user}
""",
    )
    monkeypatch.setattr(Path, "home", lambda: home)

    engine = load(project)

    assert [rule.name for rule in engine.rules] == ["same", "user-only"]
    assert [rule.event for rule in engine.rules] == [Event.SESSION_START, Event.STOP]
    assert len(engine.sources) == 2
    assert "duplicate name" in capsys.readouterr().err


def test_invalid_regex_matcher_skips_rule(tmp_path: Path, capsys) -> None:
    _write_hooks(
        tmp_path,
        """
hooks:
  - name: bad-regex
    event: PreToolUse
    if:
      all_of:
        - field: tool_name
          match: {type: regex, value: "[invalid"}
    action: {type: prompt, text: x}
""",
    )

    engine = load(tmp_path)

    assert engine.rules == []
    assert "matcher compile failed" in capsys.readouterr().err
