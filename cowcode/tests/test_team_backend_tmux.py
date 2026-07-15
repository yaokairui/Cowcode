from __future__ import annotations

from cowcode.team.backend import SpawnRequest
from cowcode.team.backend.tmux import TmuxBackend


def test_tmux_build_member_cmd_contains_agent_id() -> None:
    req = SpawnRequest(
        team_name="demo",
        member_name="alice",
        agent_id="agent-123",
        worktree_path="/tmp/wt",
        session_dir="/tmp/session",
        agent_type="general-purpose",
        model="sonnet",
        initial_prompt="hello",
        plan_mode_required=True,
    )
    cmd = TmuxBackend().build_member_cmd(req)
    assert "--team-member" in cmd
    assert "--agent-id" in cmd
    assert "agent-123" in cmd
    assert "--plan-mode" in cmd
    assert "hello" not in cmd
