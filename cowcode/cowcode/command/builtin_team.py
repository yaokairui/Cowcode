"""/team slash 命令。"""

from __future__ import annotations

import shlex


def _team_mgr(ui):
    return getattr(ui, "team_manager", None)


async def handle_team(ui, args: str) -> None:
    mgr = _team_mgr(ui)
    if mgr is None:
        ui.error("team manager not ready")
        return
    parts = shlex.split(args or "")
    if not parts or parts[0] == "list":
        teams = mgr.list_()
        if not teams:
            ui.println("没有 Team")
            return
        for team in teams:
            active = sum(1 for member in team.members if member.is_active is not False)
            ui.println(f"{team.sanitized_name}  {team.backend}  {len(team.members)} 成员  [{active}/{len(team.members)}] 活跃")
        return
    if parts[0] == "info" and len(parts) >= 2:
        team = mgr.get(parts[1])
        if team is None:
            ui.error("team not found")
            return
        ui.println(f"Team {team.sanitized_name}\nconfig: {team.config_path}")
        for member in team.members:
            ui.println(f"- {member.name} {member.agent_id} {member.backend_type} active={member.is_active} worktree={member.worktree_path}")
        return
    if parts[0] == "delete" and len(parts) >= 2:
        await mgr.delete(parts[1], "--force" in parts)
        ui.println("team deleted")
        return
    if parts[0] == "kill" and len(parts) >= 2:
        target = parts[1]
        for team in mgr.list_():
            member = team.member_by_name(target) or team.member_by_agent_id(target)
            if member is None:
                continue
            from cowcode.team.backend import new_backend

            await new_backend(member.backend_type, task_mgr=mgr.task_mgr).kill(member.pane_id, member.agent_id)
            await mgr.remove_member(team, member.name)
            ui.println("member killed")
            return
        ui.error("member not found")
        return
    ui.error("用法: /team list | /team info <name> | /team delete <name> [--force] | /team kill <member>")
