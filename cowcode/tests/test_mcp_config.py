from __future__ import annotations

from pathlib import Path

from cowcode.mcp.config import load_config


def test_two_layers_merge_and_expand(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    (home / ".cowcode").mkdir(parents=True)
    project.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("TOKEN", "secret")
    (home / ".cowcode" / "config.yaml").write_text(
        """mcp_servers:
  shared:
    type: stdio
    command: user-command
  user-only:
    type: http
    url: https://user.example/mcp
    headers:
      Authorization: Bearer ${TOKEN}
""",
        encoding="utf-8",
    )
    (project / ".cowcode.yaml").write_text(
        """mcp_servers:
  shared:
    type: stdio
    command: project-command
    args: ["${TOKEN}"]
""",
        encoding="utf-8",
    )

    config = load_config(str(project))

    assert set(config.servers) == {"shared", "user-only"}
    assert config.servers["shared"].command == "project-command"
    assert config.servers["shared"].args == ["${TOKEN}"]
    assert config.servers["user-only"].headers["Authorization"] == "Bearer secret"


def test_invalid_file_and_servers_are_skipped(tmp_path, monkeypatch, capsys) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    (home / ".cowcode").mkdir(parents=True)
    project.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    (home / ".cowcode" / "config.yaml").write_text("mcp_servers: [", encoding="utf-8")
    (project / ".cowcode.yaml").write_text(
        """mcp_servers:
  missing-command:
    type: stdio
  bad-type:
    type: websocket
  valid:
    type: http
    url: https://example.com/mcp
    headers:
      Authorization: ${MISSING_TOKEN}
""",
        encoding="utf-8",
    )

    config = load_config(str(project))

    assert set(config.servers) == {"valid"}
    assert config.servers["valid"].headers["Authorization"] == ""
    error = capsys.readouterr().err
    assert "load" in error
    assert "missing-command" in error
    assert "bad-type" in error
    assert "MISSING_TOKEN" in error
