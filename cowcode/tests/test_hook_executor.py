"""Hook Executor 测试。"""

from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from cowcode.hook.executor import Executor
from cowcode.hook.event import Event
from cowcode.hook.rule import ActionType, HttpAction, PromptAction, Rule, ShellAction, SubagentAction


def _rule(action_type: ActionType, action, *, timeout: float = 1.0) -> Rule:
    return Rule(
        name="test-hook",
        event=Event.PRE_TOOL_USE,
        condition=None,
        action_type=action_type,
        action=action,
        timeout=timeout,
    )


@pytest.mark.asyncio
async def test_shell_exit_2_blocks_with_stderr_reason() -> None:
    executor = Executor()
    rule = _rule(ActionType.SHELL, ShellAction("sh -c 'echo blocked >&2; exit 2'"))

    result = await executor.run(rule, {"event": "PreToolUse"}, blocking=True)

    assert result.blocked is True
    assert result.reason == "blocked"


@pytest.mark.asyncio
async def test_shell_exit_0_allows() -> None:
    executor = Executor()
    rule = _rule(ActionType.SHELL, ShellAction("sh -c 'exit 0'"))

    result = await executor.run(rule, {"event": "PreToolUse"}, blocking=True)

    assert result.err is None
    assert result.blocked is False


@pytest.mark.asyncio
async def test_shell_exit_1_is_error_not_block() -> None:
    executor = Executor()
    rule = _rule(ActionType.SHELL, ShellAction("sh -c 'echo bad >&2; exit 1'"))

    result = await executor.run(rule, {"event": "PreToolUse"}, blocking=True)

    assert result.err is not None
    assert result.blocked is False
    assert "exit 1" in str(result.err)


@pytest.mark.asyncio
async def test_shell_receives_sorted_json_stdin() -> None:
    executor = Executor()
    rule = _rule(ActionType.SHELL, ShellAction("sh -c 'cat >&2; exit 2'"))

    result = await executor.run(rule, {"z": 1, "a": 2}, blocking=True)

    assert result.reason == json.dumps({"a": 2, "z": 1}, sort_keys=True)


@pytest.mark.asyncio
async def test_shell_timeout_returns_timeout_error() -> None:
    executor = Executor()
    rule = _rule(ActionType.SHELL, ShellAction("sh -c 'sleep 2'"), timeout=0.1)

    result = await executor.run(rule, {"event": "PreToolUse"}, blocking=True)

    assert isinstance(result.err, TimeoutError)


def test_prompt_returns_prompt_text() -> None:
    executor = Executor()
    rule = _rule(ActionType.PROMPT, PromptAction("remember this"))

    result = executor._run_prompt(rule.action)

    assert result.prompt == "remember this"


class _Handler(BaseHTTPRequestHandler):
    response_status = 200
    response_body = b"{}"
    received_body = b""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        type(self).received_body = self.rfile.read(length)
        self.send_response(type(self).response_status)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(type(self).response_body)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


class _Server:
    def __init__(self, *, status: int = 200, body: bytes = b"{}") -> None:
        _Handler.response_status = status
        _Handler.response_body = body
        _Handler.received_body = b""
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/hook"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.server.shutdown()
        self.thread.join(timeout=1)
        self.server.server_close()


@pytest.mark.asyncio
async def test_http_block_response_blocks() -> None:
    executor = Executor()
    with _Server(body=b'{"decision":"block","reason":"x"}') as server:
        rule = _rule(ActionType.HTTP, HttpAction(url=server.url))
        result = await executor.run(rule, {"event": "PreToolUse"}, blocking=True)

    assert result.blocked is True
    assert result.reason == "x"


@pytest.mark.asyncio
async def test_http_5xx_is_error() -> None:
    executor = Executor()
    with _Server(status=500, body=b"err") as server:
        rule = _rule(ActionType.HTTP, HttpAction(url=server.url))
        result = await executor.run(rule, {"event": "PreToolUse"}, blocking=True)

    assert result.err is not None
    assert "http 500" in str(result.err)


@pytest.mark.asyncio
async def test_http_body_template_uses_payload_fields() -> None:
    executor = Executor()
    with _Server(body=b"{}") as server:
        rule = _rule(ActionType.HTTP, HttpAction(url=server.url, body="event={event}"))
        result = await executor.run(rule, {"event": "PreToolUse"}, blocking=True)

    assert result.err is None
    assert _Handler.received_body == b"event=PreToolUse"


def test_subagent_stub_logs_fixed_message(capsys) -> None:
    executor = Executor()

    result = executor._run_subagent(SubagentAction("foo", "test"))

    assert result.err is None
    assert "[hook subagent] not yet implemented, skipped: foo" in capsys.readouterr().err
