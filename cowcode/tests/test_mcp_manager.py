from __future__ import annotations

import asyncio

import pytest

from cowcode.mcp import Config, ServerConfig
from cowcode.mcp import manager as manager_module
from cowcode.mcp.manager import new_manager


@pytest.mark.asyncio
async def test_empty_manager_closes() -> None:
    manager = await new_manager(Config(), version="test")
    assert manager.tools() == []
    assert manager.connected_server_count() == 0
    await manager.close()
    await manager.close()


@pytest.mark.asyncio
async def test_failure_isolated_and_tools_sorted(monkeypatch, capsys) -> None:
    async def fake_connect(manager, name, server, version):
        if name == "bad":
            raise RuntimeError("failed")
        await asyncio.sleep(0 if name == "a" else 0.01)
        async with manager._lock:
            manager._tools.append(
                type("Tool", (), {"full_name": f"mcp__{name}__echo"})()
            )

    monkeypatch.setattr(manager_module, "_do_connect", fake_connect)
    config = Config(
        servers={
            "z": ServerConfig(type="stdio", command="z"),
            "bad": ServerConfig(type="stdio", command="bad"),
            "a": ServerConfig(type="stdio", command="a"),
        }
    )

    manager = await new_manager(config, version="test")

    assert [tool.full_name for tool in manager.tools()] == [
        "mcp__a__echo",
        "mcp__z__echo",
    ]
    assert manager.connected_server_count() == 0
    assert "bad" in capsys.readouterr().err
    await manager.close()


@pytest.mark.asyncio
async def test_connect_and_close_timeouts(monkeypatch, capsys) -> None:
    async def blocked_connect(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(manager_module, "_do_connect", blocked_connect)
    monkeypatch.setattr(manager_module, "connect_timeout", 0.01)
    manager = await new_manager(
        Config(servers={"slow": ServerConfig(type="stdio", command="slow")}),
        version="test",
    )
    assert "timeout" in capsys.readouterr().err

    class BlockingStack:
        async def aclose(self):
            await asyncio.Event().wait()

    manager._stack = BlockingStack()
    monkeypatch.setattr(manager_module, "close_timeout", 0.01)
    await manager.close()
    assert "close timeout" in capsys.readouterr().err
