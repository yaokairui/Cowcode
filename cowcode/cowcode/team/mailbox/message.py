"""邮箱消息类型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class MessageType(StrEnum):
    TEXT = "text"
    SHUTDOWN_REQUEST = "shutdown_request"
    SHUTDOWN_RESPONSE = "shutdown_response"
    PLAN_APPROVAL_RESPONSE = "plan_approval_response"


@dataclass
class Message:
    from_: str
    to: str
    type: MessageType = MessageType.TEXT
    summary: str = ""
    content: str = ""
    payload: dict[str, Any] | None = None
    timestamp: int = 0
    read: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_,
            "to": self.to,
            "type": str(self.type),
            "summary": self.summary,
            "content": self.content,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "read": self.read,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Message":
        return cls(
            from_=str(data.get("from", "")),
            to=str(data.get("to", "")),
            type=MessageType(str(data.get("type") or MessageType.TEXT)),
            summary=str(data.get("summary", "") or ""),
            content=str(data.get("content", "") or ""),
            payload=data.get("payload")
            if isinstance(data.get("payload"), dict)
            else None,
            timestamp=int(data.get("timestamp", 0) or 0),
            read=bool(data.get("read", False)),
        )
