from __future__ import annotations

import pytest

from cowcode.config import ConfigError, load


def test_load_valid_config(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
providers:
  - name: Local OpenAI
    protocol: openai
    api_key: literal-key
    model: test-model
system_prompt: custom
""".strip(),
        encoding="utf-8",
    )

    config = load(str(config_path))

    assert len(config.providers) == 1
    assert config.providers[0].name == "Local OpenAI"
    assert config.providers[0].base_url == "https://api.openai.com/v1"
    assert config.system_prompt == "custom"


def test_missing_required_field_raises_config_error(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
providers:
  - name: Broken
    protocol: openai
    api_key: literal-key
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="model"):
        load(str(config_path))


def test_invalid_protocol_raises_config_error(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
providers:
  - name: Broken
    protocol: unknown
    api_key: literal-key
    model: test-model
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Invalid protocol"):
        load(str(config_path))


def test_missing_file_raises_config_error(tmp_path) -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        load(str(tmp_path / "missing.yaml"))
