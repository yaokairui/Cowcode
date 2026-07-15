"""AgentTool worktree isolation helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from cowcode.agent import Event
from cowcode.tool.ctx import with_cwd
from cowcode.worktree import Manager, random_agent_name


def build_worktree_notice(parent_cwd: str, wt_path: str) -> str:
    return f"""<worktree-context>
你当前在一个独立的 Git Worktree 副本中工作,与父 Agent 隔离。
- 父目录: {parent_cwd}
- 你的工作目录: {wt_path}
- 父 Agent 提到的绝对路径基于父目录,你需要翻译成本地路径(替换前缀)再读写
- 编辑文件前,必须先在本地 Worktree 重新 read_file 一次,避免使用过时内容
</worktree-context>"""


async def execute_with_worktree(
    manager: Manager,
    sub_agent: Any,
    sub_session: Any,
    prompt: str,
    events: asyncio.Queue[Event | None],
) -> str:
    name = random_agent_name()
    wt = await manager.create(name, "HEAD", manual=False)  # type: ignore[attr-defined]
    notice = build_worktree_notice(str(Path.cwd()), wt.path)
    task_text = notice + "\n\n" + prompt
    try:
        with with_cwd(wt.path):
            final_text = await sub_agent.run_to_completion(
                sub_session, task_text, events
            )
    finally:
        report = await manager.auto_cleanup(name)  # type: ignore[attr-defined]
    if report.kept:
        final_text += f"\n[Worktree 保留: {report.path}, 分支 {report.branch}]"
    return final_text
