from __future__ import annotations

from cowcode.permission import Mode
from cowcode.subagent import Source, builtin_definitions, load_catalog, parse_definition


def _agent_doc(**overrides: object) -> bytes:
    fields = {
        "name": "Explore",
        "description": "read only explorer",
    }
    fields.update(overrides)
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        else:
            lines.append(f"{key}: {value}")
    lines.extend(["---", "", "body text"])
    return "\n".join(lines).encode()


def test_parse_definition_full() -> None:
    definition = parse_definition(
        _agent_doc(
            tools=["read_file"],
            disallowedTools=["write_file"],
            model="haiku",
            maxTurns=7,
            permissionMode="dontAsk",
            background=True,
        ),
        "agent.md",
        Source.PROJECT,
    )

    assert definition.name == "Explore"
    assert definition.tools == ["read_file"]
    assert definition.disallowed_tools == ["write_file"]
    assert definition.model == "haiku"
    assert definition.max_turns == 7
    assert definition.dont_ask is True
    assert definition.permission_mode == Mode.DEFAULT
    assert definition.background is True
    assert definition.system_prompt == "body text"


def test_parse_definition_invalid_fields_fallback(capsys) -> None:
    definition = parse_definition(
        _agent_doc(model="gpt-4", permissionMode="weird"),
        "agent.md",
        Source.USER,
    )

    assert definition.model == "inherit"
    assert definition.permission_mode == Mode.DEFAULT
    stderr = capsys.readouterr().err
    assert "unknown model" in stderr
    assert "unknown permissionMode" in stderr


def test_builtin_definitions_load() -> None:
    names = {definition.name for definition in builtin_definitions()}

    assert {"general-purpose", "Explore", "Plan"}.issubset(names)


def test_catalog_project_overrides_builtin(tmp_path) -> None:
    agent_dir = tmp_path / ".cowcode" / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "explore.md").write_text(
        "---\nname: Explore\ndescription: project override\n---\n\nproject body",
        encoding="utf-8",
    )

    catalog = load_catalog(tmp_path)
    definition = catalog.resolve("Explore")

    assert definition is not None
    assert definition.source == Source.PROJECT
    assert definition.system_prompt == "project body"
    assert catalog.fork_definition().is_fork() is True
