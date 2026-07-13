"""slash 输入解析。"""

from __future__ import annotations


def parse(input_text: str) -> tuple[str, bool]:
    """解析输入是否为 slash 命令，返回命令名与是否 slash。"""

    text = input_text.strip()
    if not text.startswith("/"):
        return "", False
    tail = text[1:]
    if not tail:
        return "", True
    parts = tail.split(maxsplit=1)
    if not parts or not parts[0] or parts[0].startswith("/"):
        return "", True
    if len(parts) > 1 and parts[1].strip():
        return "", True
    return parts[0].lower(), True
