"""/worktree slash command."""

from __future__ import annotations

from cowcode.command.ui import UI


async def _noop(_ui: UI) -> None:
    return None


async def handle_worktree(ui: UI, args: str) -> None:
    accessor = ui.worktree_accessor()
    if accessor is None:
        ui.error("Worktree 功能未启用")
        return

    parts = args.split()
    if not parts:
        ui.error("用法: /worktree create|list|enter|exit|remove ...")
        return
    cmd = parts[0]
    rest = parts[1:]
    if cmd == "create":
        if len(rest) != 1:
            ui.error("用法: /worktree create <slug>")
            return
        path, branch = await accessor.create(rest[0])
        ui.println(f"Worktree 已创建: {path} (分支 {branch})")
    elif cmd == "list":
        rows = accessor.list()
        if not rows:
            ui.println("没有 Worktree")
            return
        for row in rows:
            flags = []
            if row.active:
                flags.append("active")
            if row.manual:
                flags.append("manual")
            suffix = f" [{' '.join(flags)}]" if flags else ""
            ui.println(f"{row.name}  {row.path}  {row.branch}{suffix}")
    elif cmd == "enter":
        if len(rest) != 1:
            ui.error("用法: /worktree enter <slug>")
            return
        await accessor.enter(rest[0])
        ui.println(f"已进入 {rest[0]}")
    elif cmd == "exit":
        remove = "--remove" in rest
        discard = "--discard" in rest
        removed = await accessor.exit("remove" if remove else "keep", discard)
        ui.println("已退出并删除 Worktree" if removed else "已退出 Worktree")
    elif cmd == "remove":
        names = [item for item in rest if not item.startswith("--")]
        if len(names) != 1:
            ui.error("用法: /worktree remove <slug> [--discard]")
            return
        await accessor.remove(names[0], "--discard" in rest)
        ui.println(f"已删除 Worktree: {names[0]}")
    else:
        ui.error(f"未知 worktree 子命令: {cmd}")
