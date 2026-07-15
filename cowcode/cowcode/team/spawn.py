"""Team spawn 主流程。"""

from __future__ import annotations

import json
import secrets
from pathlib import Path

from cowcode.agent import Agent
from cowcode.agent_team import IncomingMessage, TeamSpawnRequest, TeammateContext
from cowcode.compact import AutoCompactTrackingState, ContentReplacementState, RecoveryState, new_session_context
from cowcode.permission import Mode
from cowcode.runtime import SessionRuntime
from cowcode.session import Session
from cowcode.team.backend import SpawnRequest, new_backend
from cowcode.team.mailbox import Box, Message, MessageType
from cowcode.team.types import BackendType, InProcessTeammateNoSpawnError, TeammateInfo
from cowcode.tool.filter import FilterParams, apply_agent_tool_filter

TEAM_SYSTEM_PROMPT_SUFFIX = """IMPORTANT: You are running as an agent in a team.
Just writing a response in text is not visible to others
on your team - you MUST use the SendMessage tool.
The user interacts primarily with the team lead.
Your work is coordinated through the task system
and teammate messaging."""


def team_system_prompt_suffix() -> str:
    return TEAM_SYSTEM_PROMPT_SUFFIX


def build_team_context_reminder(team, member_name: str, agent_id: str, worktree_path: str) -> str:
    members = ", ".join(member.name for member in team.members)
    return f"""<team-context>
team: {team.sanitized_name}
你的成员名: {member_name}
你的 agent_id: {agent_id}
worktree 目录: {worktree_path}
当前团队成员: {members}
</team-context>"""


def truncate_for_summary(prompt: str) -> str:
    words = prompt.strip().split()
    return " ".join(words[:10]) if words else "initial task"


async def spawn_teammate(manager, req: TeamSpawnRequest) -> str:
    team = manager.get(req.team_name)
    if team is None:
        raise ValueError(f"unknown team: {req.team_name}")
    backend_type = team.backend
    tc = req.ctx.get("teammate") if isinstance(req.ctx, dict) else None
    if tc is not None and getattr(tc, "backend_type", "") == str(BackendType.IN_PROCESS):
        raise InProcessTeammateNoSpawnError("in-process teammate cannot spawn team members")
    member_name = req.member_name or f"agent-{secrets.token_hex(3)}"
    agent_id = "agent-" + secrets.token_hex(7)
    wt_name = f"team-{team.sanitized_name}/{member_name}"
    wt = None
    if manager.wt_mgr is not None:
        wt = await manager.wt_mgr.create(wt_name, "HEAD", manual=False)
        worktree_path = wt.path
        branch = wt.branch
    else:
        worktree_path = str(manager.project_root / ".cowcode" / "worktrees" / f"team-{team.sanitized_name}+{member_name}")
        Path(worktree_path).mkdir(parents=True, exist_ok=True)
        branch = f"worktree-team-{team.sanitized_name}+{member_name}"
    session_dir = str(manager.project_root / ".cowcode" / "sessions" / agent_id)
    definition = None
    if getattr(manager, "catalog", None) is not None and req.subagent_type:
        definition = manager.catalog.resolve(req.subagent_type)
    if definition is None and getattr(manager, "catalog", None) is not None:
        definition = manager.catalog.resolve("general-purpose")
    source = int(getattr(definition, "source", 0)) if definition is not None else 0
    allowed = apply_agent_tool_filter(
        FilterParams(
            all=manager.registry_tools.names() if getattr(manager, "registry_tools", None) is not None else [],
            source=source,
            background=False,
            allowed=list(getattr(definition, "tools", []) or []),
            disallowed=list(getattr(definition, "disallowed_tools", []) or []),
            teammate=True,
        )
    )
    mailbox = Box(team.mailbox_dir)

    async def _read_unread():
        indices, messages = await mailbox.read_unread(agent_id)
        return indices, [
            IncomingMessage(
                from_=msg.from_,
                type=str(msg.type),
                summary=msg.summary,
                content=msg.content,
                payload=msg.payload,
                timestamp=msg.timestamp,
            )
            for msg in messages
        ]

    async def _mark_read(indices: list[int]) -> None:
        await mailbox.mark_read(agent_id, indices)

    teammate_ctx = TeammateContext(
        team_name=team.sanitized_name,
        member_name=member_name,
        agent_id=agent_id,
        backend_type=str(backend_type),
        read_unread=_read_unread,
        mark_read=_mark_read,
    )
    sub_agent = None
    sub_session = None
    if backend_type == BackendType.IN_PROCESS:
        parent = req.parent
        if parent is None:
            raise RuntimeError("parent agent missing")
        prompt = getattr(definition, "system_prompt", "") or parent._system_prompt
        prompt = (prompt.rstrip() + "\n\n" + TEAM_SYSTEM_PROMPT_SUFFIX).strip()
        sub_agent = Agent(
            parent._provider,
            parent._registry,
            system_prompt=prompt,
            environment=parent._environment,
            engine=parent._engine,
            runtime=SessionRuntime(
                replacement=ContentReplacementState(),
                recovery=RecoveryState(),
                auto_tracking=AutoCompactTrackingState(),
                session=new_session_context(worktree_path),
            ),
            allowed_tools=allowed,
            hook_engine=parent._hook_engine,
            max_turns=getattr(definition, "max_turns", 0) if definition is not None else 0,
            permission_mode=Mode.PLAN if req.plan_mode_required else getattr(definition, "permission_mode", Mode.DEFAULT),
            dont_ask=True,
            approval_upgrader=manager.task_mgr.upgrade_approval,
            include_system_tools=False,
            ctx={"teammate": teammate_ctx},
        )
        sub_session = Session()
        sub_session.append("system", build_team_context_reminder(team, member_name, agent_id, worktree_path))
    else:
        await mailbox.write(
            agent_id,
            Message(
                from_="lead",
                to=agent_id,
                type=MessageType.TEXT,
                summary=truncate_for_summary(req.prompt),
                content=req.prompt,
            ),
        )
    spawn_req = SpawnRequest(
        team_name=team.sanitized_name,
        member_name=member_name,
        agent_id=agent_id,
        worktree_path=worktree_path,
        session_dir=session_dir,
        agent_type=req.subagent_type,
        model=req.model,
        initial_prompt=req.prompt,
        plan_mode_required=req.plan_mode_required,
        sub_agent=sub_agent,
        conv=sub_session,
        task_mgr=manager.task_mgr,
    )
    backend = new_backend(backend_type, task_mgr=manager.task_mgr)
    pane_id, actual_agent_id = await backend.spawn(spawn_req)
    info = TeammateInfo(
        name=member_name,
        agent_id=actual_agent_id,
        agent_type=req.subagent_type,
        model=req.model,
        worktree_path=worktree_path,
        branch=branch,
        backend_type=backend_type,
        pane_id=pane_id,
        is_active=True,
        plan_mode_required=req.plan_mode_required,
        session_dir=session_dir,
    )
    manager.registry.register(member_name, actual_agent_id)
    await manager.add_member(team, info)
    return json.dumps(
        {
            "member_name": member_name,
            "agent_id": actual_agent_id,
            "worktree": worktree_path,
            "backend": str(backend_type),
            "pane_id": pane_id,
        },
        ensure_ascii=False,
    )
