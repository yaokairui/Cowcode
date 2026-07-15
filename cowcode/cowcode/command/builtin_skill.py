"""Skill 列表 slash 命令。"""

from __future__ import annotations

from cowcode.command.ui import UI


async def handle_skill(ui: UI) -> None:
    """输出当前已加载的 Skill 精简列表。"""

    skills = sorted(ui.list_catalog_skills(), key=lambda item: item.name)
    if not skills:
        ui.println("No skills loaded.")
        return
    ui.println(f"Available skills ({len(skills)}):")
    width = max(len(item.name) for item in skills)
    for item in skills:
        ui.println(f"  /{item.name:<{width}}  {item.description}")
    ui.println("Type /<skill-name> to invoke a skill.")
