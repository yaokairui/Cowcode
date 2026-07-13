"""slash 命令注册中心测试。"""

from __future__ import annotations

import pytest

from cowcode.command import Command, Kind, Registry
from cowcode.command.ui import NopUI


async def noop(ui: NopUI) -> None:
    pass


def cmd(
    name: str, *, aliases: list[str] | None = None, hidden: bool = False
) -> Command:
    return Command(
        name=name,
        description=f"{name} desc",
        kind=Kind.LOCAL,
        handler=noop,
        aliases=aliases or [],
        hidden=hidden,
    )


def test_register_ok() -> None:
    reg = Registry()
    reg.register(cmd("help", aliases=["h"]))
    assert reg.lookup("help") is reg.lookup("H")
    assert reg.lookup("h") is reg.lookup("help")


def test_register_duplicate_name_raises() -> None:
    reg = Registry()
    reg.register(cmd("help"))
    with pytest.raises(RuntimeError, match="help"):
        reg.register(cmd("help"))


def test_register_duplicate_alias_raises() -> None:
    reg = Registry()
    reg.register(cmd("help", aliases=["h"]))
    with pytest.raises(RuntimeError, match="h"):
        reg.register(cmd("hello", aliases=["h"]))


def test_visible_sorted_and_hidden_filtered() -> None:
    reg = Registry()
    reg.register(cmd("status"))
    reg.register(cmd("clear"))
    reg.register(cmd("secret", hidden=True))
    assert [item.name for item in reg.visible()] == ["clear", "status"]


def test_prefix_match() -> None:
    reg = Registry()
    reg.register(cmd("status"))
    reg.register(cmd("session", aliases=["s"]))
    reg.register(cmd("help", aliases=["status-alias"]))
    assert [item.name for item in reg.prefix_match("/s")] == ["session", "status"]
    assert [item.name for item in reg.prefix_match("/")] == [
        "help",
        "session",
        "status",
    ]
