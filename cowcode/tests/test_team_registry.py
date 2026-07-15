from __future__ import annotations

from cowcode.team.registry import AgentNameRegistry


def test_agent_name_registry_register_resolve_reverse() -> None:
    reg = AgentNameRegistry()
    reg.register("alice", "agent-123")
    assert reg.resolve("alice") == "agent-123"
    assert reg.resolve("agent-123") == "agent-123"
    assert reg.name_of("agent-123") == "alice"

    reg.register("alice", "agent-456")
    assert reg.resolve("alice") == "agent-456"
    assert reg.name_of("agent-123") is None

    reg.register("bob", "agent-456")
    assert reg.resolve("alice") is None
    assert reg.name_of("agent-456") == "bob"
