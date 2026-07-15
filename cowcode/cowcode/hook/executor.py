"""Hook 动作执行器。"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass

import httpx

from cowcode.hook.rule import (
    ActionType,
    HttpAction,
    Payload,
    PromptAction,
    Rule,
    ShellAction,
    SubagentAction,
)


@dataclass(frozen=True)
class ExecutionResult:
    blocked: bool = False
    reason: str = ""
    prompt: str = ""
    err: Exception | None = None


class Executor:
    """执行 shell / prompt / http / subagent 四类 hook 动作。"""

    def __init__(self) -> None:
        self._http_client = httpx.AsyncClient()

    async def run(self, rule: Rule, payload: Payload, *, blocking: bool) -> ExecutionResult:
        if rule.action_type == ActionType.SHELL and isinstance(rule.action, ShellAction):
            return await self._run_shell(rule.action, payload, blocking, rule.timeout)
        if rule.action_type == ActionType.PROMPT and isinstance(rule.action, PromptAction):
            return self._run_prompt(rule.action)
        if rule.action_type == ActionType.HTTP and isinstance(rule.action, HttpAction):
            return await self._run_http(rule.action, payload, blocking, rule.timeout)
        if rule.action_type == ActionType.SUBAGENT and isinstance(rule.action, SubagentAction):
            return self._run_subagent(rule.action)
        return ExecutionResult(err=RuntimeError("invalid hook action"))

    async def _run_shell(
        self, action: ShellAction, payload: Payload, blocking: bool, timeout: float
    ) -> ExecutionResult:
        proc = await asyncio.create_subprocess_shell(
            action.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(_marshal_sorted(payload)), timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.wait()
            return ExecutionResult(err=TimeoutError(str(exc)))
        reason = (stderr or stdout).decode(errors="replace").rstrip("\n")
        if blocking and proc.returncode == 2:
            return ExecutionResult(blocked=True, reason=reason)
        if proc.returncode == 0:
            return ExecutionResult()
        return ExecutionResult(err=RuntimeError(f"exit {proc.returncode}: {reason}"))

    def _run_prompt(self, action: PromptAction) -> ExecutionResult:
        return ExecutionResult(prompt=action.text)

    async def _run_http(
        self, action: HttpAction, payload: Payload, blocking: bool, timeout: float
    ) -> ExecutionResult:
        try:
            body = (
                _marshal_sorted(payload).decode()
                if action.body is None
                else action.body.format_map(payload)
            )
            response = await self._http_client.request(
                action.method or "POST",
                action.url,
                content=body,
                headers=action.headers,
                timeout=timeout,
            )
            if not (200 <= response.status_code < 300):
                return ExecutionResult(err=RuntimeError(f"http {response.status_code}"))
            if not blocking:
                return ExecutionResult()
            data = json.loads(response.text or "{}")
            if data.get("decision") == "block":
                return ExecutionResult(blocked=True, reason=str(data.get("reason", "")))
            return ExecutionResult()
        except (httpx.HTTPError, httpx.TimeoutException, ValueError, KeyError) as exc:
            return ExecutionResult(err=exc)

    def _run_subagent(self, action: SubagentAction) -> ExecutionResult:
        print(
            f"[hook subagent] not yet implemented, skipped: {action.agent_name}",
            file=sys.stderr,
        )
        return ExecutionResult()


def _marshal_sorted(payload: Payload) -> bytes:
    return json.dumps(payload, sort_keys=True).encode()
