"""第 2 层：LLM 摘要与历史重建。"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from cowcode.compact.const import (
    ESTIMATE_CHARS_PER_TOKEN,
    PTL_DROP_PERCENTAGE,
    PTL_RETRY_LIMIT,
    RECENT_KEEP_MESSAGES,
    RECENT_KEEP_TOKENS,
)
from cowcode.compact.recovery import build_recovery_attachment
from cowcode.compact.summary_prompt import build_summary_prompt, extract_summary
from cowcode.compact.token import estimate_tokens, message_chars
from cowcode.provider import Request
from cowcode.provider.base import PromptTooLongError
from cowcode.session import Message

if TYPE_CHECKING:
    from cowcode.compact.compact import ManageInput


def _has_tool_calls(msg: Message) -> bool:
    return msg.role == "assistant" and bool(msg.tool_calls)


def pick_recent_tail(msgs: list[Message]) -> list[Message]:
    """从尾部保留近期原文，并避免 tool_result 落单。"""

    if not msgs:
        return []
    total_chars = 0
    count = 0
    start_idx = len(msgs)
    for index in range(len(msgs) - 1, -1, -1):
        total_chars += message_chars([msgs[index]])
        count += 1
        start_idx = index
        if (
            math.ceil(total_chars / ESTIMATE_CHARS_PER_TOKEN) >= RECENT_KEEP_TOKENS
            and count >= RECENT_KEEP_MESSAGES
        ):
            break
    while start_idx > 0 and msgs[start_idx].role == "tool":
        start_idx -= 1
        if _has_tool_calls(msgs[start_idx]):
            break
    return list(msgs[start_idx:])


def _join_after_summary(
    summary_and_recovery: Message, recent: list[Message]
) -> list[Message]:
    if not recent:
        return [summary_and_recovery]
    recent = list(recent)
    while recent and recent[0].role == "tool":
        recent.pop(0)
    if recent and recent[0].role == "user":
        return [
            summary_and_recovery,
            Message(
                role="assistant", content="（已加载上下文摘要与恢复信息。请继续。）"
            ),
            *recent,
        ]
    return [summary_and_recovery, *recent]


def group_by_user_turn(msgs: list[Message]) -> list[list[Message]]:
    """按 user 消息切分历史组。"""

    groups: list[list[Message]] = []
    current: list[Message] = []
    for msg in msgs:
        if msg.role == "user" and current:
            groups.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        groups.append(current)
    return groups


async def summarize_once(in_: "ManageInput", msgs: list[Message]) -> str:
    """发起一次不带工具的摘要请求。"""

    request = Request(messages=build_summary_prompt(msgs), tools=[])
    text: list[str] = []
    async for ev in in_.provider.stream(request):
        if ev.err is not None:
            raise ev.err
        if ev.text:
            text.append(ev.text)
    return extract_summary("".join(text))


async def ptl_retry(
    in_: "ManageInput", msgs: list[Message], first_err: Exception
) -> str:
    """摘要请求自身过长时，逐步丢弃旧消息组后重试。"""

    groups = group_by_user_turn(msgs)
    last_err: Exception = first_err
    retry_count = 0
    while groups:
        if retry_count < PTL_RETRY_LIMIT:
            drop = 1
        else:
            drop = max(1, math.ceil(len(groups) * PTL_DROP_PERCENTAGE))
        groups = groups[drop:]
        if not groups:
            break
        retry_count += 1
        retry_msgs = [msg for group in groups for msg in group]
        try:
            return await summarize_once(in_, retry_msgs)
        except PromptTooLongError as exc:
            last_err = exc
            continue
    raise last_err


async def run_summary(in_: "ManageInput") -> list[Message]:
    """执行摘要、拼恢复段和近期原文。"""

    old_msgs = in_.conv.get_history()
    recovery_snapshot = in_.recovery.snapshot()
    try:
        summary_text = await summarize_once(in_, old_msgs)
    except PromptTooLongError as exc:
        summary_text = await ptl_retry(in_, old_msgs, exc)
    recovery_text = build_recovery_attachment(recovery_snapshot, in_.tool_defs)
    combined = Message(
        role="user",
        content="## 历史会话摘要\n" + summary_text + "\n\n" + recovery_text,
    )
    return _join_after_summary(combined, pick_recent_tail(old_msgs))


async def auto_compact(in_: "ManageInput") -> tuple[list[Message], int, int]:
    before = in_.estimated_token
    try:
        new_msgs = await run_summary(in_)
    except Exception:
        in_.auto_tracking.record_failure()
        raise
    in_.auto_tracking.record_success()
    after = estimate_tokens(0, new_msgs, 0)
    return new_msgs, before, after


async def force_compact(in_: "ManageInput") -> tuple[list[Message], int, int]:
    before = in_.estimated_token
    new_msgs = await run_summary(in_)
    after = estimate_tokens(0, new_msgs, 0)
    return new_msgs, before, after
