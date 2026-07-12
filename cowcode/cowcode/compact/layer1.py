"""第 1 层：工具结果落盘与预览替换。"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from cowcode.compact.const import (
    MESSAGE_AGGREGATE_LIMIT,
    PREVIEW_HEAD_BYTES,
    PREVIEW_HEAD_LINES,
    SINGLE_RESULT_LIMIT,
)
from cowcode.compact.state import ContentReplacementState, SessionContext
from cowcode.session import Message

_LOG = logging.getLogger(__name__)


def _utf8_len(text: str) -> int:
    return len((text or "").encode("utf-8"))


def _trim_utf8(text: str, byte_limit: int) -> str:
    data = text.encode("utf-8")[:byte_limit]
    return data.decode("utf-8", errors="ignore")


def _head_preview(content: str) -> str:
    lines = content.splitlines(keepends=True)[:PREVIEW_HEAD_LINES]
    head = "".join(lines)
    if _utf8_len(head) > PREVIEW_HEAD_BYTES:
        head = _trim_utf8(head, PREVIEW_HEAD_BYTES)
    return head


def spill_single(session: SessionContext, tool_use_id: str, content: str) -> None:
    """把完整工具结果写入 spill_dir/<tool_use_id>，已存在则跳过。"""

    path = Path(session.spill_dir) / tool_use_id
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def build_preview(original_bytes: int, head: str, spill_path: str) -> str:
    """构造稳定预览替换体。"""

    return "\n".join(
        [
            f"[content offloaded] original size: {original_bytes} bytes",
            f"[saved to] {spill_path}",
            "[head preview]",
            head.rstrip("\n"),
            "完整内容已保存到上述路径，如需查看请用文件读取工具读取该路径，不要凭头部预览猜测全文。",
        ]
    )


def offload_and_snip(
    msgs: list[Message],
    state: ContentReplacementState,
    session: SessionContext,
) -> list[Message]:
    """按单条与聚合阈值替换工具结果，返回新消息列表。"""

    out = copy.deepcopy(msgs)
    for msg in out:
        if msg.role != "tool" or not msg.tool_results:
            continue

        candidates: list[tuple[int, int, str, int]] = []
        for index, result in enumerate(msg.tool_results):
            content = result.content or ""
            tool_use_id = result.tool_call_id
            if state.is_seen(tool_use_id):
                result.content = state.decide_once(tool_use_id, content, lambda: ("kept", ""))
                continue
            candidates.append((index, _utf8_len(content), content, len(candidates)))

        remaining = sum(size for _, size, _, _ in candidates)
        ordered = sorted(candidates, key=lambda item: (-item[1], item[3]))
        replace_indexes: set[int] = set()
        for index, size, _content, _order in ordered:
            if size > SINGLE_RESULT_LIMIT:
                replace_indexes.add(index)
                remaining -= size
        for index, size, _content, _order in ordered:
            if remaining <= MESSAGE_AGGREGATE_LIMIT:
                break
            if index in replace_indexes:
                continue
            replace_indexes.add(index)
            remaining -= size

        for index, _size, content, _order in candidates:
            result = msg.tool_results[index]
            tool_use_id = result.tool_call_id
            if index in replace_indexes:

                def decide(
                    id_: str = tool_use_id,
                    original: str = content,
                ) -> tuple[str, str]:
                    try:
                        spill_single(session, id_, original)
                    except OSError as exc:
                        _LOG.warning("工具结果落盘失败: %s", exc)
                        return "skip", ""
                    spill_path = str(Path(session.spill_dir) / id_)
                    return (
                        "replaced",
                        build_preview(_utf8_len(original), _head_preview(original), spill_path),
                    )

                result.content = state.decide_once(tool_use_id, content, decide)
            else:
                result.content = state.decide_once(tool_use_id, content, lambda: ("kept", ""))
    return out
