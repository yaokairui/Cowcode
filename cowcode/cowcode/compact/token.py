"""Token 粗估算。"""

from __future__ import annotations

import json
import math
from typing import Any

from cowcode.compact.const import ESTIMATE_CHARS_PER_TOKEN
from cowcode.session import Message, Usage


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def usage_anchor(usage: Usage) -> int:
    """把 provider usage 合并成单一锚点。"""

    return int(
        usage.input_tokens
        + usage.output_tokens
        + usage.cache_read
        + usage.cache_write
    )


def _json_len(value: Any) -> int:
    if isinstance(value, str):
        return _utf8_len(value)
    try:
        return _utf8_len(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except TypeError:
        return _utf8_len(str(value))


def message_chars(msgs: list[Message]) -> int:
    """估算消息列表序列化后的 UTF-8 字节量。"""

    total = 0
    for msg in msgs:
        total += _utf8_len(msg.role)
        total += _utf8_len(msg.content or "")
        for call in msg.tool_calls:
            total += _utf8_len(call.id) + _utf8_len(call.name) + _json_len(call.input)
        for result in msg.tool_results:
            total += _utf8_len(result.tool_call_id)
            total += _utf8_len(result.content or "")
            total += 4 if result.is_error else 5
    return total


def estimate_tokens(anchor: int, all_msgs: list[Message], anchor_msg_len: int) -> int:
    """锚定真实 usage，再估算锚点后的新增消息。"""

    start = max(0, anchor_msg_len)
    tail = all_msgs[start:] if start <= len(all_msgs) else []
    return int(anchor) + math.ceil(message_chars(tail) / ESTIMATE_CHARS_PER_TOKEN)
