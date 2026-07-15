"""Skill catalog loading and validation."""

from __future__ import annotations

import os
import shutil
import sys
import threading
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

from cowcode.skills.parser import parse_skill_dir
from cowcode.skills.types import Skill, SkillSource

if TYPE_CHECKING:
    from cowcode.tool import Registry


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    skill_name: str
    tool_name: str


class Catalog:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._by_name: dict[str, Skill] = {}
        self._order: list[str] = []

    @classmethod
    def load(cls, work_dir: Path) -> "Catalog":
        catalog = cls()
        _load_builtin_into(catalog)
        _load_dir_into(catalog, Path.home() / ".cowcode" / "skills", SkillSource.USER)
        _load_dir_into(catalog, work_dir / ".cowcode" / "skills", SkillSource.PROJECT)
        return catalog

    def reload(self, work_dir: Path) -> None:
        fresh = self.load(work_dir)
        with self._lock:
            self._by_name = fresh._by_name
            self._order = fresh._order

    def register(self, skill: Skill) -> None:
        with self._lock:
            if skill.meta.name not in self._by_name:
                self._order.append(skill.meta.name)
            self._by_name[skill.meta.name] = skill
            self._order = sorted(set(self._order))

    def remove(self, name: str) -> None:
        with self._lock:
            self._by_name.pop(name, None)
            self._order = [item for item in self._order if item != name]

    def get(self, name: str) -> Skill | None:
        with self._lock:
            return self._by_name.get(name)

    def list(self) -> list[Skill]:
        with self._lock:
            return [
                self._by_name[name] for name in self._order if name in self._by_name
            ]

    def names(self) -> list[str]:
        with self._lock:
            return list(self._order)

    def validate_tools(self, registry: "Registry") -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        builtin_allowed = {"load_skill", "install_skill", "LoadSkill", "InstallSkill"}
        for skill in self.list():
            own_tools = {spec.name for spec in skill.tool_specs}
            for tool_name in skill.meta.allowed_tools:
                if tool_name in builtin_allowed or tool_name in own_tools:
                    continue
                if registry.get(tool_name) is None:
                    issues.append(ValidationIssue(skill.meta.name, tool_name))
        return issues


def _load_dir_into(catalog: Catalog, base_dir: Path, source: SkillSource) -> None:
    if not base_dir.is_dir():
        return
    for child in sorted(base_dir.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        try:
            skill = parse_skill_dir(child, source)
        except Exception as exc:
            print(f"skill {child}: {exc}, skipped", file=sys.stderr)
            continue
        catalog.register(skill)


def _load_builtin_into(catalog: Catalog) -> None:
    try:
        base = files("cowcode.skills.builtin")
    except Exception as exc:
        print(f"builtin skills unavailable: {exc}", file=sys.stderr)
        return
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    target_root = cache_root / "cowcode" / "builtin-skills"
    for entry in base.iterdir():
        if not entry.is_dir() or not entry.joinpath("SKILL.md").is_file():
            continue
        target = target_root / entry.name
        try:
            if target.exists():
                shutil.rmtree(target)
            _copy_traversable(entry, target)
            catalog.register(parse_skill_dir(target, SkillSource.BUILTIN))
        except Exception as exc:
            print(f"builtin skill {entry.name}: {exc}, skipped", file=sys.stderr)


def _copy_traversable(src, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for child in src.iterdir():
        child_dst = dst / child.name
        if child.is_dir():
            _copy_traversable(child, child_dst)
        else:
            child_dst.write_bytes(child.read_bytes())
