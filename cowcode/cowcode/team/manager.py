"""Team 管理器。"""

from __future__ import annotations

import asyncio
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from cowcode.team.backend import new_backend
from cowcode.team.backend.detect import detect
from cowcode.team.mailbox import Box, Message, MessageType
from cowcode.team.persistence import attach_paths, atomic_write_json, read_json, sanitize
from cowcode.team.registry import AgentNameRegistry
from cowcode.team.types import (
    BackendType,
    Team,
    TeamHasActiveMembersError,
    TeamNotFoundError,
    TeammateInfo,
)
from cowcode.worktree import ExitOptions


@dataclass
class LeadMessage:
    team_name: str
    from_: str
    type: str
    summary: str
    content: str
    timestamp: int


class Manager:
    def __init__(self, home_dir: str | Path, project_root: str | Path, wt_mgr, task_mgr, registry: AgentNameRegistry | None = None) -> None:
        self.home_dir = Path(home_dir)
        self.project_root = Path(project_root)
        self.wt_mgr = wt_mgr
        self.task_mgr = task_mgr
        self.registry = registry or AgentNameRegistry()
        self.catalog = None
        self.registry_tools = None
        self._lock = asyncio.Lock()
        self.base_dir = self.home_dir / ".cowcode" / "teams"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.teams: dict[str, Team] = {}
        self._load_existing()

    def get(self, name: str) -> Team | None:
        return self.teams.get(sanitize(name)) or self.teams.get(name)

    def list_(self) -> list[Team]:
        return sorted(self.teams.values(), key=lambda item: item.created_at)

    async def spawn_teammate(self, req) -> str:
        from cowcode.team.spawn import spawn_teammate

        return await spawn_teammate(self, req)

    def is_teammate_context(self, ctx) -> tuple[str, str, bool]:
        from cowcode.agent_team import teammate_context_from_ctx

        tc = teammate_context_from_ctx(ctx)
        if tc is None:
            return "", "", False
        return tc.team_name, tc.member_name, tc.backend_type == str(BackendType.IN_PROCESS)

    async def create(self, name: str, description: str = "") -> Team:
        slug = sanitize(name)
        if not slug:
            raise ValueError("team name is empty after sanitize")
        async with self._lock:
            unique = slug
            index = 2
            while unique in self.teams or (self.base_dir / unique).exists():
                unique = f"{slug}-{index}"
                index += 1
            team = attach_paths(
                Team(
                    name=name,
                    sanitized_name=unique,
                    lead_agent_id="lead",
                    backend=detect(),
                    description=description,
                    members=[TeammateInfo(name="lead", agent_id="lead", is_active=None)],
                ),
                self.base_dir,
            )
            Path(team.mailbox_dir).mkdir(parents=True, exist_ok=True)
            atomic_write_json(team.config_path, team.to_dict())
            self.teams[team.sanitized_name] = team
            self.registry.register("lead", "lead")
            return team

    async def delete(self, name: str, force: bool = False) -> None:
        async with self._lock:
            team = self.get(name)
            if team is None:
                raise TeamNotFoundError(name)
            if not force and any(member.is_active is not False for member in team.members):
                raise TeamHasActiveMembersError(name)
            members = list(team.members)
            self.teams.pop(team.sanitized_name, None)
        for member in members:
            if member.name == "lead":
                continue
            backend = new_backend(member.backend_type, task_mgr=self.task_mgr)
            try:
                await backend.kill(member.pane_id, member.agent_id)
            except Exception as exc:
                print(f"team delete: kill {member.name} failed: {exc}", file=sys.stderr)
            await self._cleanup_member_resources(member)
        shutil.rmtree(team.config_dir, ignore_errors=True)

    async def add_member(self, team: Team, info: TeammateInfo) -> None:
        await team.add_member(info)

    async def set_member_active(self, team: Team, name: str, active: bool) -> None:
        await team.set_member_active(name, active)

    async def remove_member(self, team: Team, name: str) -> None:
        await team.remove_member(name)

    async def handle_task_done(self, agent_id: str) -> None:
        name = self.registry.name_of(agent_id)
        if not name:
            return
        for team in self.list_():
            member = team.member_by_agent_id(agent_id)
            if member is None:
                continue
            try:
                await self.set_member_active(team, member.name, False)
            except Exception:
                pass
            await Box(team.mailbox_dir).write(
                team.lead_agent_id,
                Message(
                    from_=member.name,
                    to=team.lead_agent_id,
                    type=MessageType.TEXT,
                    summary=f"{member.name} idle",
                    content=f"agent {agent_id} finished work, available for new tasks",
                ),
            )
            return

    async def poll_lead_mailboxes(self) -> list[LeadMessage]:
        out: list[LeadMessage] = []
        for team in self.list_():
            box = Box(team.mailbox_dir)
            indices, messages = await box.read_unread(team.lead_agent_id)
            if not messages:
                continue
            await box.mark_read(team.lead_agent_id, indices)
            out.extend(
                LeadMessage(
                    team_name=team.sanitized_name,
                    from_=msg.from_,
                    type=str(msg.type),
                    summary=msg.summary,
                    content=msg.content,
                    timestamp=msg.timestamp,
                )
                for msg in messages
            )
        return out

    async def _cleanup_member_resources(self, member: TeammateInfo) -> None:
        if member.session_dir:
            shutil.rmtree(member.session_dir, ignore_errors=True)
        if self.wt_mgr is not None and member.worktree_path:
            name = f"team-{member.branch}" if not member.branch else member.branch.removeprefix("worktree-").replace("+", "/")
            try:
                await self.wt_mgr.remove(name, ExitOptions(discard_changes=True))
            except Exception:
                pass

    def _load_existing(self) -> None:
        for child in self.base_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                data = read_json(child / "config.json")
                team = attach_paths(Team.from_dict(data), self.base_dir)
            except Exception as exc:
                print(f"team: skip broken config {child}: {exc}", file=sys.stderr)
                continue
            if team.backend == BackendType.IN_PROCESS:
                for member in team.members:
                    if member.name != "lead":
                        member.is_active = False
            self.teams[team.sanitized_name] = team
            for member in team.members:
                self.registry.register(member.name, member.agent_id)
