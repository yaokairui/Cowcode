"""黑名单——内置不可配置的危险命令正则。"""

import re

# 启发式、非完备防御。以下模式不可被任何配置、规则或模式放开（含 bypassPermissions）。
_BLACKLIST: list[re.Pattern] = [
    # rm -rf 根/家目录及变体
    re.compile(r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+([\"']?\s*(/|~|\$HOME|/\*)\s*[\"']?)"),
    # 写块设备（含 dd 重写设备头）
    re.compile(r"\bdd\b.*\bof=\s*/dev/(sd|hd|nvme|xvd|vd|disk|loop|mapper)"),
    # fork bomb
    re.compile(r":\s*\(\)\s*\{.*\|\s*&\s*\};?"),
    # 格式化文件系统
    re.compile(r"\bmk(?:fs|dosfs|ext[234]|btrfs|xfs|ntfs)\.?\s"),
    # 重定向覆盖磁盘设备
    re.compile(r">\s*/dev/(sd|hd|nvme|xvd|vd|disk|loop|mapper)"),
    # chmod 递归 777 /
    re.compile(r"\bchmod\s+-R\s+0?777\s+/"),
    # chown 递归 /
    re.compile(r"\bchown\s+-R\s+\S+\s*/"),
    # mkswap 覆盖
    re.compile(r"\bmkswap\s+/dev/"),
    # wipefs
    re.compile(r"\bwipefs\s+(-[a-zA-Z]*a[a-zA-Z]*\s+)?/dev/"),
]


def hits_blacklist(command: str) -> bool:
    """命令串命中任一危险模式返回 True。"""
    return any(p.search(command) for p in _BLACKLIST)
