"""路径沙箱——防软链接逃逸。"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_root(root: str) -> str:
    """将根目录解析为绝对路径，失败抛 FileNotFoundError。"""
    return str(Path(root).expanduser().resolve(strict=True))


def eval_symlinks_or_ancestor(abs_path: str) -> str:
    """解析符号链接；目标不存在时回退到最近已存在祖先目录后拼回剩余段。"""
    p = Path(abs_path)
    if p.exists():
        return str(p.resolve(strict=True))
    # 回退到最近存在的祖先
    missing: list[str] = []
    while not p.exists() and p.parent != p:
        missing.append(p.name)
        p = p.parent
    if p.exists():
        base = str(p.resolve(strict=True))
    else:
        return abs_path  # 极少见：路径完全不可解析，保留原值让前缀判定兜底
    if not missing:
        return base
    missing.reverse()
    return os.path.join(base, *missing)


def sandbox_ok(root: str, path: str) -> bool:
    """判断路径是否落在项目根内（先 resolve 再前缀比对）。"""
    root_resolved = root.rstrip(os.sep)
    if not path or not path.strip():
        return True  # 空路径视为 root
    raw_norm = path.replace("\\", "/")
    if raw_norm == "/tmp" or raw_norm.startswith("/tmp/"):
        return True
    if raw_norm == "/private/tmp" or raw_norm.startswith("/private/tmp/"):
        return True
    if os.name == "nt" and raw_norm.startswith("/"):
        return False
    abs_path = os.path.join(root_resolved, path) if not os.path.isabs(path) else path
    try:
        resolved = eval_symlinks_or_ancestor(abs_path)
    except (OSError, ValueError, RuntimeError):
        return False
    resolved_clean = resolved.rstrip(os.sep)
    return resolved_clean == root_resolved or resolved_clean.startswith(
        root_resolved + os.sep
    )
