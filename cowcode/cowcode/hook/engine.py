"""Hook 分派引擎。"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field

from cowcode.hook.event import Event, is_blocking
from cowcode.hook.executor import Executor
from cowcode.hook.matcher import eval_condition
from cowcode.hook.rule import Payload, Rule


@dataclass
class DispatchResult:
    blocked: bool = False
    reason: str = ""
    blocking_hook_name: str = ""
    injected_prompts: list[str] = field(default_factory=list)


class Engine:
    """按事件分派 hook 规则。"""

    def __init__(self, rules: list[Rule], sources: list[str]) -> None:
        self._rules = list(rules)
        self._sources = list(sources)
        self._lock = asyncio.Lock()
        self._once_fired: set[str] = set()
        self._executor = Executor()

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    @property
    def sources(self) -> list[str]:
        return list(self._sources)

    async def dispatch(self, event: Event, payload: Payload) -> DispatchResult:
        result = DispatchResult()
        for rule in self._rules:
            if rule.event != event:
                continue
            async with self._lock:
                if rule.only_once and rule.name in self._once_fired:
                    continue
            if not eval_condition(rule.condition, payload):
                continue
            if rule.asyncio_mode:
                asyncio.create_task(self._run_async_rule(rule, payload))
                if rule.only_once:
                    async with self._lock:
                        self._once_fired.add(rule.name)
                continue
            outcome = await self._executor.run(
                rule, payload, blocking=is_blocking(event)
            )
            if outcome.err is not None:
                print(
                    f"[hook {rule.name}] {event.value} failed: {outcome.err}",
                    file=sys.stderr,
                )
                continue
            if outcome.prompt:
                result.injected_prompts.append(outcome.prompt)
            if rule.only_once:
                async with self._lock:
                    self._once_fired.add(rule.name)
            if outcome.blocked and is_blocking(event):
                result.blocked = True
                result.reason = outcome.reason
                result.blocking_hook_name = rule.name
                break
        return result

    async def reset_for_new_session(self) -> None:
        async with self._lock:
            self._once_fired.clear()

    async def _run_async_rule(self, rule: Rule, payload: Payload) -> None:
        outcome = await self._executor.run(rule, payload, blocking=False)
        if outcome.err is not None:
            print(
                f"[hook {rule.name}] {rule.event.value} failed: {outcome.err}",
                file=sys.stderr,
            )
