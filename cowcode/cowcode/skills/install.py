"""Install Skill from a zip URL."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import httpx

from cowcode.skills.catalog import Catalog
from cowcode.skills.parser import is_valid_skill_name

_MAX_ZIP_BYTES = 50 * 1024 * 1024


async def install_from_url(source: str, catalog: Catalog, work_dir: Path) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        tmp_path = Path(tmp.name)
    try:
        total = 0
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", source) as response:
                response.raise_for_status()
                with tmp_path.open("wb") as fh:
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > _MAX_ZIP_BYTES:
                            raise ValueError("zip too large")
                        fh.write(chunk)
        with zipfile.ZipFile(tmp_path) as zf:
            top_dir = _validate_zip(zf)
            target = Path.home() / ".cowcode" / "skills" / top_dir
            if target.exists():
                shutil.rmtree(target)
            for info in zf.infolist():
                if info.is_dir():
                    continue
                rel = PurePosixPath(info.filename)
                out_path = Path.home() / ".cowcode" / "skills" / Path(*rel.parts)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, out_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        catalog.reload(work_dir)
        return top_dir
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _validate_zip(zf: zipfile.ZipFile) -> str:
    names = [
        info.filename
        for info in zf.infolist()
        if info.filename and not info.filename.endswith("/")
    ]
    if not names:
        raise ValueError("zip contains no files")
    top_dirs: set[str] = set()
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        path = PurePosixPath(name)
        parts = path.parts
        if not parts or path.is_absolute() or ".." in parts:
            raise ValueError("unsafe path in zip")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise ValueError("unsafe path in zip")
        top_dirs.add(parts[0])
    if len(top_dirs) != 1:
        raise ValueError("zip must contain exactly one top-level skill directory")
    top_dir = next(iter(top_dirs))
    if not is_valid_skill_name(top_dir):
        raise ValueError(f"invalid skill directory name: {top_dir}")
    if f"{top_dir}/SKILL.md" not in {name.replace("\\", "/") for name in names}:
        raise ValueError("zip does not contain SKILL.md")
    return top_dir
