"""Load bundled SubAgent definitions."""

from __future__ import annotations

from importlib.resources import files

from cowcode.subagent.definition import Definition, Source
from cowcode.subagent.parser import parse_definition


def builtin_definitions() -> list[Definition]:
    package = files("cowcode.subagent.builtin")
    definitions: list[Definition] = []
    for item in package.iterdir():
        if item.name.endswith(".md"):
            data = item.read_bytes()
            definitions.append(
                parse_definition(data, f"builtin:{item.name}", Source.BUILTIN)
            )
    return sorted(definitions, key=lambda item: item.name.lower())
