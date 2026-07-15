"""Adapters from skills state to prompt render inputs."""

from __future__ import annotations

from dataclasses import dataclass

from cowcode.skills.active import ActiveSkills
from cowcode.skills.catalog import Catalog


@dataclass(frozen=True)
class PromptItem:
    name: str
    description: str


@dataclass(frozen=True)
class PromptEntry:
    name: str
    body: str


def catalog_to_prompt_items(catalog: Catalog) -> list[PromptItem]:
    return [PromptItem(s.meta.name, s.meta.description) for s in catalog.list()]


def active_to_prompt_entries(active: ActiveSkills) -> list[PromptEntry]:
    return [PromptEntry(entry.name, entry.body) for entry in active.snapshot()]
