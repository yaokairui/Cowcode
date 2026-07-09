"""Abstract Provider interface for Cowcode."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from cowcode.session import Session, StreamEvent, ToolDefinition

__all__ = ["Provider", "ProviderError"]


class ProviderError(Exception):
    """Provider 调用失败时抛出的可读错误。"""


class Provider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def stream(
        self, session: Session, tools: list[ToolDefinition] | None = None
    ) -> AsyncIterator[StreamEvent]:
        """Stream model events from the LLM."""
