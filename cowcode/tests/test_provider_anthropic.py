"""Anthropic ch05 请求构造测试。"""

from cowcode.config import ProviderConfig
from cowcode.provider import Request, SystemPrompt
from cowcode.provider.anthropic import AnthropicProvider
from cowcode.session import Message, ToolDefinition, ToolResult


def _provider() -> AnthropicProvider:
    return AnthropicProvider(
        ProviderConfig(
            name="test",
            protocol="anthropic",
            model="test-model",
            api_key="secret",
        )
    )


def test_anthropic_payload_separates_cached_system_and_environment() -> None:
    request = Request(
        messages=[Message(role="user", content="hello")],
        tools=[ToolDefinition("read_file", "read", {"type": "object"})],
        system=SystemPrompt(stable="stable", environment="environment"),
        reminder="<system-reminder>plan</system-reminder>",
    )
    payload = _provider().build_payload(request)

    assert payload["system"] == [
        {
            "type": "text",
            "text": "stable",
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": "environment"},
    ]
    assert payload["tools"][0]["name"] == "read_file"
    assert payload["messages"][-1]["content"][-1]["text"] == request.reminder
    assert request.messages[0].content == "hello"


def test_anthropic_usage_fields_are_optional() -> None:
    assert AnthropicProvider._parse_start_usage(
        {
            "input_tokens": 12,
            "cache_creation_input_tokens": 8,
            "cache_read_input_tokens": 4,
        }
    ) == (12, 8, 4)
    assert AnthropicProvider._parse_start_usage(None) == (0, 0, 0)
    assert AnthropicProvider._parse_output_usage({"output_tokens": 5}) == 5
    assert AnthropicProvider._parse_output_usage(None) == 0


def test_anthropic_reminder_follows_tool_results() -> None:
    request = Request(
        messages=[
            Message(
                role="tool",
                tool_results=[ToolResult("call-1", "result")],
            )
        ],
        reminder="runtime reminder",
    )
    content = _provider().build_payload(request)["messages"][0]["content"]
    assert [block["type"] for block in content] == ["tool_result", "text"]
    assert content[-1]["text"] == "runtime reminder"
