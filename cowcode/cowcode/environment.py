"""Cowcode 运行环境采集。"""

from __future__ import annotations

import datetime as dt
import os
import platform
import subprocess
from dataclasses import dataclass

__all__ = ["Environment", "gather_environment"]


@dataclass(frozen=True)
class Environment:
    """提供给模型的非缓存运行环境信息。"""

    working_dir: str = ""
    platform: str = ""
    date: str = ""
    git_status: str = ""
    version: str = ""
    model: str = ""

    def render(self) -> str:
        """渲染非空环境字段。"""
        values = [
            ("Working directory", self.working_dir),
            ("Platform", self.platform),
            ("Date", self.date),
            ("Git status", self.git_status),
            ("Cowcode version", self.version),
            ("Model", self.model),
        ]
        return "Runtime environment:\n" + "\n".join(
            f"- {name}: {value}" for name, value in values if value
        )


def gather_environment(version: str, model: str, timeout: float = 2.0) -> Environment:
    """快速采集环境；git 不可用、超时或非仓库时自动降级。"""
    try:
        working_dir = os.getcwd()
    except OSError:
        working_dir = ""

    git_status = ""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=working_dir or None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0:
            lines = [line for line in result.stdout.splitlines() if line.strip()]
            git_status = "clean" if not lines else f"{len(lines)} changed paths"
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass

    return Environment(
        working_dir=working_dir,
        platform=platform.platform(),
        date=dt.date.today().isoformat(),
        git_status=git_status,
        version=version,
        model=model,
    )
