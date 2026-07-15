"""Pane 后端 team-member 入口。"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from cowcode.team.mailbox import Box, Message, MessageType


@dataclass
class TeamMemberArgs:
    team: str
    member: str
    agent_id: str
    session_dir: str
    worktree: str
    agent_type: str = ""
    model: str = ""
    plan_mode: bool = False


def parse_team_member_args(argv: list[str]) -> TeamMemberArgs:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--team-member", action="store_true")
    parser.add_argument("--team", required=True)
    parser.add_argument("--member", required=True)
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--agent-type", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--plan-mode", action="store_true")
    ns, _ = parser.parse_known_args(argv)
    return TeamMemberArgs(
        team=ns.team,
        member=ns.member,
        agent_id=ns.agent_id,
        session_dir=ns.session_dir,
        worktree=ns.worktree,
        agent_type=ns.agent_type,
        model=ns.model,
        plan_mode=ns.plan_mode,
    )


async def run_team_member(args: TeamMemberArgs) -> int:
    """最小自治循环：纯文本日志流，不启动 TUI。"""

    os.chdir(args.worktree)
    print(f"team-member {args.member} ({args.agent_id}) ready", flush=True)
    # Pane 后端真实长期循环依赖完整 LLM wire；这里先提供不启动 TUI的安全入口。
    mailbox_dir = Path.home() / ".cowcode" / "teams" / args.team / "mailbox"
    box = Box(mailbox_dir)
    while mailbox_dir.exists():
        indices, messages = await box.read_unread(args.agent_id)
        if messages:
            await box.mark_read(args.agent_id, indices)
            for msg in messages:
                print(f"Text from {msg.from_}: {msg.summary}\n{msg.content}", flush=True)
                if msg.type == MessageType.SHUTDOWN_REQUEST:
                    await box.write(
                        "lead",
                        Message(
                            from_=args.member,
                            to="lead",
                            type=MessageType.SHUTDOWN_RESPONSE,
                            summary="shutdown approved",
                            content="team member exiting",
                            payload={"approve": True},
                        ),
                    )
                    return 0
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            await asyncio.sleep(2)
    return 0
