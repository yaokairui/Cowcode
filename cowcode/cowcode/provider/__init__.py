"""Provider package for Cowcode.

Exports the Provider abstract base class, concrete implementations,
and a factory function to create the appropriate backend based on config.
"""

from cowcode.provider.anthropic import AnthropicProvider
from cowcode.provider.base import (
    Provider,
    ProviderError,
    PromptTooLongError,
    Request,
    SystemPrompt,
)
from cowcode.provider.openai import OpenAIProvider

__all__ = [
    "Provider",
    "ProviderError",
    "PromptTooLongError",
    "Request",
    "SystemPrompt",
    "AnthropicProvider",
    "OpenAIProvider",
    "create_provider",
]

_PROVIDER_MAP = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def create_provider(config) -> Provider:
    """Create a Provider instance based on the configuration."""

    provider_cls = _PROVIDER_MAP.get(config.protocol)
    if provider_cls is None:
        raise ValueError(
            f"Unsupported protocol: {config.protocol!r}. "
            f"Choose from: {list(_PROVIDER_MAP.keys())}"
        )
    return provider_cls(config)
