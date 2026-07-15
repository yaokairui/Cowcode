from __future__ import annotations

from cowcode.skills.catalog import Catalog
from cowcode.skills.types import Skill, SkillMeta, SkillSource


class DummyRegistry:
    def __init__(self, names: set[str]) -> None:
        self.names = names

    def get(self, name: str):
        return object() if name in self.names else None


def _skill(
    name: str, description: str, allowed_tools: list[str] | None = None
) -> Skill:
    return Skill(
        meta=SkillMeta(
            name=name,
            description=description,
            allowed_tools=allowed_tools or [],
        ),
        prompt_body="body",
        source_dir=__import__("pathlib").Path("."),
        source=SkillSource.PROJECT,
    )


def test_catalog_register_orders_names() -> None:
    catalog = Catalog()
    catalog.register(_skill("test", "Test"))
    catalog.register(_skill("commit", "Commit"))

    assert catalog.names() == ["commit", "test"]


def test_catalog_register_overrides_same_name() -> None:
    catalog = Catalog()
    catalog.register(_skill("commit", "Old"))
    catalog.register(_skill("commit", "New"))

    assert catalog.names() == ["commit"]
    assert catalog.get("commit").meta.description == "New"  # type: ignore[union-attr]


def test_validate_tools_missing_tool() -> None:
    catalog = Catalog()
    catalog.register(_skill("foo", "Foo", ["read_file", "NotExist"]))

    issues = catalog.validate_tools(DummyRegistry({"read_file"}))  # type: ignore[arg-type]

    assert len(issues) == 1
    assert issues[0].skill_name == "foo"
    assert issues[0].tool_name == "NotExist"


def test_validate_tools_allows_system_tool_names() -> None:
    catalog = Catalog()
    catalog.register(_skill("foo", "Foo", ["load_skill", "install_skill"]))

    assert catalog.validate_tools(DummyRegistry(set())) == []  # type: ignore[arg-type]
