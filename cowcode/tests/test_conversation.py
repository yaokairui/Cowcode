from __future__ import annotations

from cowcode.conversation import Conversation


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
