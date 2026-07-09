"""Provider package for Cowcode.

Exports the Provider abstract base class, concrete implementations,
and a factory function to create the appropriate backend based on config.
"""

from cowcode.provider.anthropic import AnthropicProvider
from cowcode.provider.base import Provider, ProviderError
from cowcode.provider.openai import OpenAIProvider

__all__ = ["Provider", "ProviderError", "AnthropicProvider", "OpenAIProvider", "create_provider"]

_PROVIDER_MAP = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def create_provider(config) -> Provider:
    """Create a Provider instance based on the configuration.

    Args:
        config: A ProviderConfig object with protocol, model, base_url, api_key.

    Returns:
        An instance of the appropriate Provider subclass.

    Raises:
        ValueError: If config.protocol is not supported.
    """
    provider_cls = _PROVIDER_MAP.get(config.protocol)
    if provider_cls is None:
        raise ValueError(
            f"Unsupported protocol: {config.protocol!r}. "
            f"Choose from: {list(_PROVIDER_MAP.keys())}"
        )
    return provider_cls(config)
