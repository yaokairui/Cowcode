"""跨进程文件锁。"""

from __future__ import annotations

import asyncio
import os
import random
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

LOCK_MAX_RETRIES = 10
LOCK_STALE_AFTER = 10.0
LOCK_BACKOFF_MIN = 0.005
LOCK_BACKOFF_MAX = 0.1


@asynccontextmanager
async def acquire(lock_path: str | Path) -> AsyncIterator[None]:
    path = Path(lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    for _ in range(LOCK_MAX_RETRIES):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, str(os.getpid()).encode())
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > LOCK_STALE_AFTER:
                    path.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            await asyncio.sleep(random.uniform(LOCK_BACKOFF_MIN, LOCK_BACKOFF_MAX))
    if fd is None:
        raise TimeoutError(f"lock busy: {path}")
    try:
        yield
    finally:
        os.close(fd)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
