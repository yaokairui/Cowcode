"""Abstract Provider interface for Cowcode."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator

from cowcode.session import Message, StreamEvent, ToolDefinition

__all__ = [
    "Provider",
    "ProviderError",
    "PromptTooLongError",
    "Request",
    "SystemPrompt",
]


class ProviderError(Exception):
    """Provider 调用失败时抛出的可读错误。"""


class PromptTooLongError(Exception):
    """Provider 上报上下文超出窗口时统一使用的哨兵异常。"""


@dataclass(frozen=True)
class SystemPrompt:
    """稳定可缓存提示与动态环境段。"""

    stable: str = ""
    environment: str = ""


@dataclass(frozen=True)
class Request:
    """一次 Provider 请求的协议无关快照。"""

    messages: list[Message] = field(default_factory=list)
    tools: list[ToolDefinition] = field(default_factory=list)
    system: SystemPrompt = field(default_factory=SystemPrompt)
    reminder: str = ""


class Provider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def model(self) -> str:
        """返回当前模型名。"""

    @abstractmethod
    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """流式执行不可变请求快照。"""
