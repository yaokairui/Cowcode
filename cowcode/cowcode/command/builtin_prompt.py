"""提示词类 slash 命令。"""

from __future__ import annotations

from cowcode import prompt
from cowcode.command.ui import UI
from cowcode.permission import Mode

REVIEW_DIRECTIVE = (
    "请审查当前上下文中的代码变更/已读取的文件，指出潜在 bug、可读性问题和可简化处。"
)


async def handle_do(ui: UI) -> None:
    ui.set_mode(Mode.DEFAULT)
    ui.inject_and_send("/do", prompt.EXECUTE_DIRECTIVE)


async def handle_review(ui: UI) -> None:
    ui.inject_and_send("/review", REVIEW_DIRECTIVE)
