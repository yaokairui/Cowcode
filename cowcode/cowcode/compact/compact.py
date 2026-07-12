"""上下文管理编排入口。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from cowcode.compact.const import AUTO_SAFETY_MARGIN, SUMMARY_RESERVE
from cowcode.compact.layer1 import offload_and_snip
from cowcode.compact.layer2 import auto_compact, force_compact
from cowcode.compact.state import (
    AutoCompactTrackingState,
    ContentReplacementState,
    RecoveryState,
    SessionContext,
)
from cowcode.compact.token import estimate_tokens
from cowcode.provider import Provider
from cowcode.session import ToolDefinition

_LOG = logging.getLogger(__name__)


class TriggerKind(Enum):
    """上下文管理触发来源。"""

    AUTO = "auto"
    MANUAL = "manual"
    EMERGENCY = "emergency"


@dataclass
class ManageInput:
    """一次上下文管理调用的入参。"""

    conv: object
    provider: Provider
    context_window: int
    tool_defs: list[ToolDefinition]
    replacement: ContentReplacementState
    recovery: RecoveryState
    auto_tracking: AutoCompactTrackingState
    session: SessionContext
    usage_anchor: int
    anchor_msg_len: int
    estimated_token: int
    trigger: TriggerKind


@dataclass
class ManageOutput:
    """上下文管理后的 token 估算。"""

    before_tokens: int
    after_tokens: int


def _history(conv: object):
    if hasattr(conv, "get_history"):
        return conv.get_history()
    if hasattr(conv, "messages"):
        value = getattr(conv, "messages")
        return value() if callable(value) else list(value)
    return []


def _replace(conv: object, messages) -> None:
    if hasattr(conv, "replace_messages"):
        conv.replace_messages(messages)
        return
    raise TypeError("conversation object must provide replace_messages")


async def manage_context(in_: ManageInput) -> ManageOutput:
    """执行第 1 层落盘与必要时的第 2 层摘要。"""

    if in_.trigger == TriggerKind.MANUAL:
        new_msgs, _before, after = await force_compact(in_)
        _replace(in_.conv, new_msgs)
        _LOG.info("context compacted trigger=manual before=%s after=%s", in_.estimated_token, after)
        return ManageOutput(in_.estimated_token, after)

    if in_.trigger == TriggerKind.EMERGENCY:
        layer1_out = offload_and_snip(_history(in_.conv), in_.replacement, in_.session)
        _replace(in_.conv, layer1_out)
        new_msgs, _before, after = await force_compact(in_)
        _replace(in_.conv, new_msgs)
        _LOG.info("context compacted trigger=emergency before=%s after=%s", in_.estimated_token, after)
        return ManageOutput(in_.estimated_token, after)

    layer1_out = offload_and_snip(_history(in_.conv), in_.replacement, in_.session)
    _replace(in_.conv, layer1_out)
    est = estimate_tokens(in_.usage_anchor, layer1_out, in_.anchor_msg_len)
    if in_.context_window <= SUMMARY_RESERVE + AUTO_SAFETY_MARGIN:
        _LOG.warning("context_window too small, skip auto compact: %s", in_.context_window)
        return ManageOutput(in_.estimated_token, est)
    threshold = in_.context_window - SUMMARY_RESERVE - AUTO_SAFETY_MARGIN
    if est < threshold or in_.auto_tracking.tripped():
        return ManageOutput(in_.estimated_token, est)

    new_msgs, _before, after = await auto_compact(in_)
    _replace(in_.conv, new_msgs)
    _LOG.info("context compacted trigger=auto before=%s after=%s", in_.estimated_token, after)
    return ManageOutput(in_.estimated_token, after)
