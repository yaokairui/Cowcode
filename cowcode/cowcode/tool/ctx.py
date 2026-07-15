"""Tool cwd context helpers."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

_ctx_cwd: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "cwd", default=None
)


@contextmanager
def with_cwd(directory: str) -> Iterator[None]:
    if not directory:
        yield
        return
    token = _ctx_cwd.set(directory)
    try:
        yield
    finally:
        _ctx_cwd.reset(token)


def cwd_from_ctx() -> str | None:
    return _ctx_cwd.get()


def resolve_path(path: str) -> str:
    base = _ctx_cwd.get() or str(Path.cwd())
    if not path:
        return base
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str(Path(base) / p)
