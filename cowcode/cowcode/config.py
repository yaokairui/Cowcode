"""Configuration loader for Cowcode."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from cowcode.protocol_defaults import (
    DEFAULT_ANTHROPIC_CONTEXT_WINDOW,
    DEFAULT_OPENAI_CONTEXT_WINDOW,
)

__all__ = [
    "Config",
    "ProviderConfig",
    "load",
    "load_configs",
    "resolve_config_path",
    "ConfigError",
    "effective_context_window",
]


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


VALID_PROTOCOLS = ("anthropic", "openai")
_DEFAULT_BASE_URLS = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
}


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for a single LLM provider."""

    name: str
    protocol: str
    model: str
    api_key: str
    base_url: str | None = None
    thinking: bool = False
    context_window: int = 0

    def __post_init__(self) -> None:
        if self.protocol not in VALID_PROTOCOLS:
            raise ConfigError(
                f"Invalid protocol: {self.protocol!r}. Must be one of {VALID_PROTOCOLS}"
            )
        if self.base_url is None:
            object.__setattr__(self, "base_url", _DEFAULT_BASE_URLS[self.protocol])


@dataclass(frozen=True)
class Config:
    """Top-level configuration containing provider list and optional system prompt."""

    providers: list[ProviderConfig] = field(default_factory=list)
    system_prompt: str = ""

    def __post_init__(self) -> None:
        if not self.providers:
            raise ConfigError("At least one provider must be configured")


def effective_context_window(provider: ProviderConfig) -> int:
    """返回 provider 有效上下文窗口。"""

    if provider.context_window > 0:
        return provider.context_window
    if provider.protocol == "openai":
        return DEFAULT_OPENAI_CONTEXT_WINDOW
    return DEFAULT_ANTHROPIC_CONTEXT_WINDOW


def resolve_config_path(path: str = "config.yaml") -> Path:
    """返回实际使用的配置文件路径。"""

    return _resolve_config_path(path)


def load_configs(path: str = "config.yaml") -> tuple[Config, list[ProviderConfig]]:
    """Load config for existing Cowcode callers."""

    config = load(path)
    return config, config.providers


def load(path: str = "config.yaml") -> Config:
    """Load and validate configuration from a YAML file."""

    config_path = _resolve_config_path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in config file {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read config file {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a mapping")

    providers_raw = raw.get("providers", [])
    if not isinstance(providers_raw, list) or not providers_raw:
        raise ConfigError(
            "No providers configured. Add at least one 'providers' entry."
        )

    provider_configs: list[ProviderConfig] = []
    for index, provider_raw in enumerate(providers_raw):
        if not isinstance(provider_raw, dict):
            raise ConfigError(f"Provider #{index + 1}: entry must be a mapping")
        provider_configs.append(_provider_from_dict(provider_raw, index + 1))

    return Config(
        providers=provider_configs,
        system_prompt=str(raw.get("system_prompt", "") or ""),
    )


def _resolve_config_path(path: str) -> Path:
    config_path = Path(path)
    if config_path.exists():
        return config_path

    packaged_config = Path(__file__).resolve().parents[1] / path
    if packaged_config.exists():
        return packaged_config

    raise ConfigError(f"Config file not found: {path}")


def _provider_from_dict(raw: dict[str, Any], provider_number: int) -> ProviderConfig:
    required_fields = ("name", "protocol", "api_key", "model")
    for field_name in required_fields:
        if field_name not in raw or not raw[field_name]:
            raise ConfigError(
                f"Provider #{provider_number}: missing required field '{field_name}'"
            )

    protocol = str(raw["protocol"])
    api_key = _resolve_api_key(str(raw["api_key"]), provider_number)
    base_url = raw.get("base_url")
    return ProviderConfig(
        name=str(raw["name"]),
        protocol=protocol,
        model=str(raw["model"]),
        api_key=api_key,
        base_url=str(base_url) if base_url else None,
        thinking=bool(raw.get("thinking", False)),
        context_window=int(raw.get("context_window", 0) or 0),
    )


def _resolve_api_key(value: str, provider_number: int) -> str:
    """Resolve api_key literals and env:NAME / ${NAME} references."""

    if value.startswith("env:"):
        env_name = value[4:].strip()
        if not env_name:
            raise ConfigError(
                f"Provider #{provider_number}: api_key env reference is empty"
            )
        resolved = os.environ.get(env_name)
        if not resolved:
            raise ConfigError(
                f"Provider #{provider_number}: environment variable '{env_name}' is not set"
            )
        return resolved

    uses_env_marker = "$" in value or (value.startswith("%") and value.endswith("%"))
    expanded = os.path.expandvars(value)
    if uses_env_marker and expanded == value:
        raise ConfigError(
            f"Provider #{provider_number}: api_key environment variable is not set"
        )
    return expanded
