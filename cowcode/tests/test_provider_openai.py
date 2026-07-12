"""OpenAI ch05 请求构造测试。"""

from cowcode.config import ProviderConfig
from cowcode.provider import Request, SystemPrompt
from cowcode.provider.openai import OpenAIProvider
from cowcode.session import Message, ToolDefinition


def _provider() -> OpenAIProvider:
    return OpenAIProvider(
        ProviderConfig(
            name="test",
            protocol="openai",
            model="test-model",
            api_key="secret",
        )
    )


def test_openai_usage_fields_are_optional() -> None:
    assert OpenAIProvider._parse_usage(
        {
            "prompt_tokens": 12,
            "completion_tokens": 5,
            "prompt_tokens_details": {"cached_tokens": 8},
        }
    ) == (12, 5, 8)
    assert OpenAIProvider._parse_usage({"prompt_tokens_details": None}) == (0, 0, 0)
    assert OpenAIProvider._parse_usage(None) == (0, 0, 0)


def test_openai_payload_keeps_stable_prefix_and_dynamic_tail() -> None:
    request = Request(
        messages=[Message(role="user", content="hello")],
        tools=[ToolDefinition("grep", "search", {"type": "object"})],
        system=SystemPrompt(stable="stable", environment="environment"),
        reminder="<system-reminder>plan</system-reminder>",
    )
    payload = _provider().build_payload(request)

    assert payload["messages"] == [
        {"role": "system", "content": "stable\n\nenvironment"},
        {"role": "user", "content": "hello"},
        {"role": "user", "content": request.reminder},
    ]
    assert payload["tools"][0]["function"]["name"] == "grep"
    assert payload["stream_options"] == {"include_usage": True}
    assert request.messages == [Message(role="user", content="hello")]
