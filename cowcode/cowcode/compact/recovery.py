"""摘要后的恢复三段。"""

from __future__ import annotations

import json
from io import StringIO

from cowcode.compact.const import (
    ESTIMATE_CHARS_PER_TOKEN,
    RECOVERY_FILE_LIMIT,
    RECOVERY_TOKENS_PER_FILE,
)
from cowcode.compact.state import FileReadRecord
from cowcode.session import ToolDefinition

BOUNDARY_NOTICE = """需要文件原文、错误原文、用户原话时，请使用文件读取工具重新读取对应路径，不要依据摘要内容做猜测。"""


def render_file_block(rec: FileReadRecord) -> str:
    """渲染单个文件快照。"""

    content = rec.content
    char_limit = int(RECOVERY_TOKENS_PER_FILE * ESTIMATE_CHARS_PER_TOKEN)
    if len(content) > char_limit:
        content = content[:char_limit].rstrip() + "\n(content truncated)"
    return f"### {rec.path}\n[read at] {rec.timestamp.isoformat()}\n{content}\n"


def render_tools_block(defs: list[ToolDefinition]) -> str:
    """渲染当前可用工具列表。"""

    if not defs:
        return "(无)\n"
    lines: list[str] = []
    for tool in defs:
        schema = json.dumps(tool.input_schema, ensure_ascii=False, separators=(",", ":"))
        lines.append(f"- {tool.name}: {tool.description}")
        lines.append(f"  schema: {schema}")
    return "\n".join(lines) + "\n"


def build_recovery_attachment(
    snapshot: list[FileReadRecord],
    tool_defs: list[ToolDefinition],
) -> str:
    """构造最近文件、工具列表、边界提示三段。"""

    buf = StringIO()
    buf.write("## 最近读过的文件\n")
    recent = snapshot[:RECOVERY_FILE_LIMIT]
    if recent:
        for record in recent:
            buf.write(render_file_block(record))
            buf.write("\n")
    else:
        buf.write("(无)\n\n")
    buf.write("## 当前可用工具\n")
    buf.write(render_tools_block(tool_defs))
    buf.write("\n## 边界提示\n")
    buf.write(BOUNDARY_NOTICE)
    return buf.getvalue()
