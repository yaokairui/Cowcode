"""摘要 prompt 与解析。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from cowcode.session import Message

_LOG = logging.getLogger(__name__)

SUMMARY_INSTRUCTION = """你正在压缩一个编程 Agent 的历史会话。请分两阶段输出。

<analysis>
先在这里写分析草稿。草稿会被丢弃。
</analysis>

<summary>
## 1 主要请求和意图
## 2 关键技术概念
## 3 文件和代码段
## 4 错误和修复
## 5 问题解决过程
## 6 所有用户消息原文
## 7 待办任务
## 8 当前工作（最详细）
## 9 可能的下一步
</summary>

正式摘要必须放在 <summary> 标签内，必须包含以上 9 个小节。第 6 节按时间顺序逐条保留所有用户消息原文。不要调用任何工具，输出纯文本。"""


def _json(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def serialize_conversation(msgs: list[Message]) -> str:
    """把会话历史转成稳定文本。"""

    lines: list[str] = []
    for msg in msgs:
        if msg.role in {"user", "assistant", "system"}:
            lines.append(f"{msg.role}: {msg.content}")
        if msg.role == "assistant" and msg.tool_calls:
            for call in msg.tool_calls:
                lines.append(f"[call {call.name} id={call.id} args={_json(call.input)}]")
        if msg.role == "tool":
            for result in msg.tool_results:
                lines.append(
                    f"[result id={result.tool_call_id} is_error={result.is_error}] {result.content}"
                )
    return "\n".join(lines)


def build_summary_prompt(msgs: list[Message]) -> list[Message]:
    """构造无工具摘要请求消息。"""

    content = SUMMARY_INSTRUCTION + "\n\n[conversation]\n" + serialize_conversation(msgs)
    return [Message(role="user", content=content)]


def extract_summary(raw: str) -> str:
    """提取最后一个 <summary> 块，失败时返回原文。"""

    matches = re.findall(r"<summary>(.*?)</summary>", raw, re.DOTALL)
    if not matches:
        _LOG.warning("summary tags not found")
        return raw.strip()
    return matches[-1].strip()
