"""Skill command executor."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from cowcode.permission import Mode
from cowcode.session import Session
from cowcode.skills.active import ActiveSkills
from cowcode.skills.render import render_body

if TYPE_CHECKING:
    from cowcode.command.ui import UI
    from cowcode.provider import Provider
    from cowcode.skills.catalog import Catalog
    from cowcode.tool import Registry


class Executor:
    def __init__(
        self,
        catalog: "Catalog",
        active: ActiveSkills,
        registry: "Registry",
        provider_factory: Callable[[str | None], "Provider | None"] | None = None,
        runtime=None,
        engine=None,
        memory_manager=None,
    ) -> None:
        self.catalog = catalog
        self.active = active
        self.registry = registry
        self.provider_factory = provider_factory
        self.runtime = runtime
        self.engine = engine
        self.memory_manager = memory_manager

    async def execute(self, ui: "UI", name: str, args: str = "") -> None:
        skill = self.catalog.get(name)
        if skill is None:
            ui.error(f"skill not found: {name}")
            return
        fresh_body = skill.prompt_body
        try:
            _, fresh_body = _read_skill_body(skill.source_dir)
            skill.prompt_body = fresh_body
        except Exception as exc:
            print(f"skill {name}: failed to reread SKILL.md: {exc}", file=sys.stderr)
        rendered = render_body(skill, args)
        if not skill.meta.is_fork():
            ui.inject_and_send(f"/{name}", rendered)
            return
        await self._execute_fork(
            ui,
            name,
            rendered,
            skill.meta.fork_context,
            skill.meta.model,
            skill.meta.allowed_tools,
        )

    async def _execute_fork(
        self,
        ui: "UI",
        name: str,
        rendered: str,
        fork_context: str,
        model: str | None,
        allowed_tools: list[str],
    ) -> None:
        try:
            provider = self.provider_factory(model) if self.provider_factory else None
            if provider is None:
                raise RuntimeError("provider is not ready")
            from cowcode.agent import Agent

            history = []
            if fork_context == "recent":
                history = ui.recent_messages(5)
            elif fork_context == "full":
                history = ui.all_messages()
            fork_session = Session()
            for msg in history:
                fork_session.append(msg.role, msg.content)
            fork_session.append("user", rendered)
            agent = Agent(
                provider,
                self.registry,
                system_prompt="",
                environment="",
                engine=self.engine,
                runtime=None,
                memory_manager=self.memory_manager,
                allowed_tools=allowed_tools,
            )
            final_text = ""
            async for event in agent.run(fork_session, Mode.DEFAULT, asyncio.Event()):
                if event.text:
                    final_text += event.text
                if event.usage is not None and self.runtime is not None:
                    async with self.runtime.lock:
                        self.runtime.usage_anchor += (
                            event.usage.input_tokens + event.usage.output_tokens
                        )
                if event.err is not None:
                    raise event.err
                if event.done:
                    break
            if not final_text.strip():
                messages = fork_session.get_history()
                final_text = next(
                    (m.content for m in reversed(messages) if m.role == "assistant"), ""
                )
            await ui.append_assistant_message(
                final_text or "(skill produced no output)"
            )
        except BaseException as exc:
            await ui.append_assistant_message(f"[skill {name} failed: {exc}]")


def _read_skill_body(source_dir: Path) -> tuple[dict, str]:
    from cowcode.skills.parser import parse_frontmatter_and_body

    return parse_frontmatter_and_body(
        (source_dir / "SKILL.md").read_text(encoding="utf-8")
    )
