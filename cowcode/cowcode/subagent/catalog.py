"""SubAgent catalog loading."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

from cowcode.permission import Mode
from cowcode.subagent.definition import Definition, Source
from cowcode.subagent.embed import builtin_definitions
from cowcode.subagent.parser import parse_file


class Catalog:
    """Resolved SubAgent definitions, with higher-priority sources overriding."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._defs: dict[str, Definition] = {}
        self._by_source: dict[Source, list[Definition]] = {}

    def resolve(self, name: str) -> Definition | None:
        with self._lock:
            return self._defs.get(name)

    def list(self) -> list[Definition]:
        with self._lock:
            return sorted(self._defs.values(), key=lambda item: item.name.lower())

    def list_by_source(self, source: Source) -> list[Definition]:
        with self._lock:
            return sorted(
                self._by_source.get(source, []), key=lambda item: item.name.lower()
            )

    def fork_definition(self) -> Definition:
        return Definition(
            name="__fork__",
            description="Fork-based subagent",
            model="inherit",
            max_turns=25,
            permission_mode=Mode.DEFAULT,
            source=Source.BUILTIN,
        )

    def _add_all(self, definitions: list[Definition]) -> None:
        with self._lock:
            for definition in definitions:
                self._by_source.setdefault(definition.source, []).append(definition)
                current = self._defs.get(definition.name)
                if current is None or definition.source >= current.source:
                    self._defs[definition.name] = definition


def load_catalog(root: str | Path) -> Catalog:
    catalog = Catalog()
    catalog._add_all(builtin_definitions())
    catalog._add_all(_load_from_dir(Path.home() / ".cowcode" / "agents", Source.USER))
    catalog._add_all(_load_from_dir(Path(root) / ".cowcode" / "agents", Source.PROJECT))
    return catalog


def _load_from_dir(directory: Path, source: Source) -> list[Definition]:
    if not directory.is_dir():
        return []
    definitions: list[Definition] = []
    for path in sorted(directory.glob("*.md")):
        try:
            definitions.append(parse_file(path, source))
        except Exception as exc:
            print(f"subagent {path}: {exc}; skipped", file=sys.stderr)
    return definitions
