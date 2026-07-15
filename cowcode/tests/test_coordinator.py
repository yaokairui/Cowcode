from __future__ import annotations

from cowcode.coordinator import (
    allowed_tools,
    env_truthy,
    is_enabled,
    system_prompt_suffix,
)
from cowcode.config import Config, FeaturesConfig, ProviderConfig


def _cfg(flag: bool) -> Config:
    return Config(
        providers=[ProviderConfig(name="p", protocol="openai", api_key="k", model="m")],
        features=FeaturesConfig(coordinator_mode=flag),
    )


def test_env_truthy() -> None:
    assert env_truthy("1")
    assert env_truthy("true")
    assert env_truthy("yes")
    assert not env_truthy("")


def test_coordinator_double_lock(monkeypatch) -> None:
    monkeypatch.delenv("MEWCODE_COORDINATOR_MODE", raising=False)
    assert is_enabled(_cfg(False)) is False
    assert is_enabled(_cfg(True)) is False
    monkeypatch.setenv("MEWCODE_COORDINATOR_MODE", "1")
    assert is_enabled(_cfg(False)) is False
    assert is_enabled(_cfg(True)) is True


def test_coordinator_allowed_tools() -> None:
    tools = allowed_tools()
    assert "bash" in tools
    assert "write_file" not in tools
    assert "edit_file" not in tools
    assert "派出 Agent 或 SendMessage 后" in system_prompt_suffix()
