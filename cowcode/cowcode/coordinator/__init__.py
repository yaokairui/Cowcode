"""Coordinator Mode。"""

from __future__ import annotations

import os

COORDINATOR_ALLOWED_TOOLS: list[str] = [
    "Agent",
    "TeamCreate",
    "TeamDelete",
    "TaskCreate",
    "TaskGet",
    "TaskList",
    "TaskUpdate",
    "SendMessage",
    "read_file",
    "glob",
    "grep",
    "bash",
]

SYSTEM_PROMPT_SUFFIX = """你处于 Coordinator Mode。按 Research / Synthesis / Implementation / Verification 四阶段协调 Team。

关键纪律:派出 Agent 或 SendMessage 后,立刻停手等汇报。禁止马上调用 read_file / glob / grep / bash 自己继续探索;禁止用 sleep 或 TaskList 轮询凑时间。你只应该回复一行总结:已派 N 名队员探索 X,等待结果。

允许自己使用 read_file/glob/grep/bash 的场景仅限:Research 第一次目标定位;Synthesis 阶段读取队员产出的报告文件;Verification 阶段执行 git diff / git status / git merge 等收敛操作。"""


def env_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def is_enabled(cfg) -> bool:
    features = getattr(cfg, "features", None)
    if not bool(getattr(features, "coordinator_mode", False)):
        return False
    return env_truthy(os.environ.get("MEWCODE_COORDINATOR_MODE", ""))


def allowed_tools() -> list[str]:
    return list(COORDINATOR_ALLOWED_TOOLS)


def system_prompt_suffix() -> str:
    return SYSTEM_PROMPT_SUFFIX
