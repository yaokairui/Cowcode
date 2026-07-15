"""/hooks 命令。"""

from __future__ import annotations

from collections import defaultdict

from cowcode.command.ui import UI


async def handle_hooks(ui: UI) -> None:
    rules = ui.hook_rules()
    if not rules:
        ui.println("No hooks loaded.")
        return
    groups = defaultdict(list)
    for rule in rules:
        groups[rule.event.value].append(rule)
    lines: list[str] = []
    for event, event_rules in groups.items():
        lines.append(f"{event}:")
        for rule in event_rules:
            flags = []
            if rule.only_once:
                flags.append("[once]")
            if rule.asyncio_mode:
                flags.append("[async]")
            suffix = " " + " ".join(flags) if flags else ""
            lines.append(
                f"  {rule.name}  {rule.event.value}  {rule.action_type.value}{suffix}"
            )
    sources = ui.hook_sources()
    if sources:
        lines.append("Loaded from: " + ", ".join(sources))
    ui.println("\n".join(lines))
