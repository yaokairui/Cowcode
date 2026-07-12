"""MCP server 连接与生命周期管理。"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass

import mcp.types as mtypes
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from cowcode.mcp.config import Config, ServerConfig
from cowcode.mcp.tool import McpTool, adapt_tool

connect_timeout: float = 30.0
close_timeout: float = 5.0


@dataclass
class _Session:
    name: str
    session: ClientSession


class Manager:
    def __init__(self) -> None:
        self._stack = AsyncExitStack()
        self._lock = asyncio.Lock()
        self._sessions: list[_Session] = []
        self._tools: list[McpTool] = []
        self._closed = False

    def tools(self) -> list[McpTool]:
        return list(self._tools)

    def connected_server_count(self) -> int:
        """返回成功完成握手和工具发现的 server 数量。"""
        return len(self._sessions)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await asyncio.wait_for(self._stack.aclose(), timeout=close_timeout)
        except asyncio.TimeoutError:
            print(
                f"[mcp] warn: close timeout ({close_timeout:g}s), some sessions may leak",
                file=sys.stderr,
            )
        except Exception as exc:
            print(f"[mcp] warn: close failed: {exc}", file=sys.stderr)


async def new_manager(config: Config, version: str) -> Manager:
    """并发连接所有 server，失败按 server 隔离。"""

    manager = Manager()
    await manager._stack.__aenter__()
    tasks = [
        asyncio.create_task(_connect_one(manager, name, server, version))
        for name, server in config.servers.items()
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    manager._tools.sort(key=lambda tool: tool.full_name)
    return manager


async def _connect_one(
    manager: Manager, name: str, server: ServerConfig, version: str
) -> None:
    try:
        await asyncio.wait_for(
            _do_connect(manager, name, server, version), timeout=connect_timeout
        )
    except asyncio.TimeoutError:
        print(
            f"[mcp] warn: connect server {name} timeout after {connect_timeout:g}s",
            file=sys.stderr,
        )
    except Exception as exc:
        print(f"[mcp] warn: connect server {name} failed: {exc}", file=sys.stderr)


async def _do_connect(
    manager: Manager, name: str, server: ServerConfig, version: str
) -> None:
    if server.type == "stdio":
        parameters = StdioServerParameters(
            command=server.command,
            args=server.args,
            env={**os.environ, **server.env},
        )
        context = stdio_client(parameters)
    else:
        context = streamablehttp_client(server.url, headers=server.headers or None)

    transport = await manager._stack.enter_async_context(context)
    read, write = transport[0], transport[1]
    session = await manager._stack.enter_async_context(
        ClientSession(
            read,
            write,
            client_info=mtypes.Implementation(name="cowcode", version=version),
        )
    )
    await session.initialize()
    listed = await session.list_tools()
    tools = [
        adapted
        for remote in listed.tools
        if (adapted := adapt_tool(name, remote, session)) is not None
    ]
    async with manager._lock:
        manager._sessions.append(_Session(name=name, session=session))
        manager._tools.extend(tools)
