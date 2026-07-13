"""ch04 Conversation 单测——含 last_role 场景。"""

from __future__ import annotations

from cowcode.conversation import Conversation
from cowcode.session import Message, Session


def test_conversation_preserves_message_order_and_returns_copy() -> None:
    conversation = Conversation()

    conversation.add_user("hello")
    conversation.add_assistant("hi")

    messages = conversation.messages()
    assert [(message.role, message.content) for message in messages] == [
        ("user", "hello"),
        ("assistant", "hi"),
    ]

    messages.append(messages[0])
    assert len(conversation) == 2


def test_conversation_callbacks() -> None:
    appended: list[Message] = []
    replaced: list[list[Message]] = []
    conversation = Conversation(on_append=appended.append, on_replace=replaced.append)

    conversation.add_user("hello")
    conversation.add_assistant("hi")
    conversation.replace_messages([Message(role="user", content="new")])

    assert [(msg.role, msg.content) for msg in appended] == [
        ("user", "hello"),
        ("assistant", "hi"),
    ]
    assert [[(msg.role, msg.content) for msg in batch] for batch in replaced] == [
        [("user", "new")]
    ]


def test_session_callbacks() -> None:
    appended: list[Message] = []
    replaced: list[list[Message]] = []
    session = Session(on_append=appended.append, on_replace=replaced.append)

    session.append("user", "hello")
    session.append("assistant", "hi")
    session.replace_messages([Message(role="assistant", content="summary")])

    assert [(msg.role, msg.content) for msg in appended] == [
        ("user", "hello"),
        ("assistant", "hi"),
    ]
    assert replaced[0][0].content == "summary"

    """空历史 + 各角色填充后的 last_role 断言。"""
    session = Session()
    assert session.last_role() == ""

    session.append("user", "hello")
    assert session.last_role() == "user"

    session.append("assistant", "hi there")
    assert session.last_role() == "assistant"

    # 模拟 tool results 回合
    from cowcode.session import ToolResult

    session.add_tool_results([ToolResult(tool_call_id="c1", content="result")])
    assert session.last_role() == "tool"

    session.append("assistant", "final answer")
    assert session.last_role() == "assistant"
