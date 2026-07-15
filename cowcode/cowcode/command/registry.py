"""slash 命令注册中心。"""

from __future__ import annotations

from collections.abc import Callable

from cowcode.command.command import Command


class Registry:
    """维护命令名、别名与可见命令列表。"""

    def __init__(self) -> None:
        self._by_name: dict[str, Command] = {}
        self._visible: list[Command] = []

    def register(self, cmd: Command) -> None:
        keys = [cmd.name, *cmd.aliases]
        for key in keys:
            if not key or key != key.lower():
                raise RuntimeError(f"invalid command name: {key}")
            if key in self._by_name:
                raise RuntimeError(f"command conflict: {key}")
        for key in keys:
            self._by_name[key] = cmd
        if not cmd.hidden:
            self._visible.append(cmd)
            self._visible.sort(key=lambda item: item.name)

    def remove_if(self, pred: Callable[[Command], bool]) -> None:
        """按条件移除命令及其别名。"""

        removed_ids = {id(cmd) for cmd in self._visible if pred(cmd)}
        removed_ids.update(id(cmd) for cmd in self._by_name.values() if pred(cmd))
        if not removed_ids:
            return
        self._by_name = {
            key: cmd for key, cmd in self._by_name.items() if id(cmd) not in removed_ids
        }
        self._visible = [cmd for cmd in self._visible if id(cmd) not in removed_ids]

    def lookup(self, name: str) -> Command | None:
        return self._by_name.get(name.lower())

    def visible(self) -> list[Command]:
        return list(self._visible)

    def prefix_match(self, prefix: str) -> list[Command]:
        needle = prefix.lstrip("/").lower()
        return [cmd for cmd in self._visible if cmd.name.startswith(needle)]
