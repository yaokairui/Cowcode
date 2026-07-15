"""Fork SubAgent conversation helpers."""

from __future__ import annotations

import copy

from cowcode.session import Message, ToolResult

FORK_BOILERPLATE_TAG = "<fork_boilerplate>"
FORK_BOILERPLATE = """<fork_boilerplate>
你是一个 Fork 出来的工作进程。你不是主 Agent。
规则(不可协商):
1. 不能再 Fork(调用 Agent 工具会被拦截)。
2. 不要对话、不要提问、不要请求确认。
3. 直接使用工具:读文件、搜索代码、做修改。
4. 严格限制在你被分配的任务范围内。
5. 最终报告以 "Scope:" 开头,500 字以内。
</fork_boilerplate>

"""


def build_forked_messages(parent_msgs: list[Message], task: str) -> list[Message]:
    messages = copy.deepcopy(parent_msgs)
    if messages and messages[-1].role == "assistant" and messages[-1].tool_calls:
        consumed: set[str] = set()
        for msg in messages:
            if msg.role == "tool":
                consumed.update(result.tool_call_id for result in msg.tool_results)
        missing = [call.id for call in messages[-1].tool_calls if call.id not in consumed]
        if missing:
            messages.append(
                Message(
                    role="tool",
                    tool_results=[
                        ToolResult(
                            tool_call_id=call_id,
                            content="[forked, skipped]",
                            is_error=True,
                        )
                        for call_id in missing
                    ],
                )
            )
    messages.append(Message(role="user", content=FORK_BOILERPLATE + task))
    return messages


def is_fork_context(messages: list[Message]) -> bool:
    for msg in messages:
        if FORK_BOILERPLATE_TAG in msg.content:
            return True
        for result in msg.tool_results:
            if FORK_BOILERPLATE_TAG in result.content:
                return True
    return False
