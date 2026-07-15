"""队员邮箱注入。"""

from __future__ import annotations

from typing import Any

from cowcode.agent_team import IncomingMessage, teammate_context_from_ctx
from cowcode.permission import Mode


def format_incoming_messages(messages: list[IncomingMessage]) -> str:
    lines = ["<incoming-messages>", f"收到 {len(messages)} 条新消息:"]
    for index, msg in enumerate(messages, start=1):
        content = msg.content[:200]
        lines.append(
            f"[{index}] 来自 {msg.from_}(type={msg.type},ts={msg.timestamp}): {msg.summary}"
        )
        if content:
            lines.append(f"    {content}")
    lines.append("</incoming-messages>")
    return "\n".join(lines)


async def ingest_team_mailbox(agent: Any, ctx: Any) -> str:
    tc = teammate_context_from_ctx(ctx)
    if tc is None or tc.read_unread is None or tc.mark_read is None:
        return ""
    indices, messages = await tc.read_unread()
    if not messages:
        return ""
    for msg in messages:
        if msg.type == "plan_approval_response" and msg.payload:
            if msg.payload.get("approve") is True:
                if hasattr(agent, "set_permission_mode"):
                    agent.set_permission_mode(Mode.DEFAULT)
                msg.content = (
                    msg.content + "\nLead 已批准计划,权限模式已切到 default,可执行计划"
                ).strip()
            elif msg.payload.get("approve") is False:
                msg.content = (
                    msg.content
                    + f"\nLead 驳回了计划,反馈:{msg.payload.get('feedback', '')}。请调整后重新提交"
                ).strip()
    await tc.mark_read(indices)
    return format_incoming_messages(messages)
