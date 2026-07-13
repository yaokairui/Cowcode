"""slash 命令补全菜单。"""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.text import Text

from cowcode.command import Command, Registry

MAX_ROWS = 8


@dataclass(slots=True)
class CompletionMenu:
    """输入框下方的命令候选状态。"""

    items: list[Command] = field(default_factory=list)
    cursor: int = 0
    offset: int = 0
    active: bool = False

    def update(self, input_text: str, reg: Registry) -> None:
        text = input_text.strip()
        if "\n" in input_text or not text.startswith("/"):
            self.hide()
            return
        self.items = reg.prefix_match(text)
        self.active = True
        if not self.items:
            self.cursor = 0
            self.offset = 0
            return
        self.cursor = min(self.cursor, len(self.items) - 1)
        self._keep_visible()

    def move_up(self) -> None:
        if not self.items:
            return
        self.cursor = max(0, self.cursor - 1)
        self._keep_visible()

    def move_down(self) -> None:
        if not self.items:
            return
        self.cursor = min(len(self.items) - 1, self.cursor + 1)
        self._keep_visible()

    def selected(self) -> Command | None:
        if not self.items:
            return None
        return self.items[self.cursor]

    def hide(self) -> None:
        self.items = []
        self.cursor = 0
        self.offset = 0
        self.active = False

    def render(self, width: int) -> Text:
        if not self.active:
            return Text("")
        if not self.items:
            return Text("无匹配", style="dim")

        visible_count = min(MAX_ROWS, len(self.items))
        end = min(len(self.items), self.offset + visible_count)
        rows = self.items[self.offset : end]
        name_width = max(len(item.name) for item in self.items)
        out = Text()
        if self.offset > 0:
            out.append(f"↑ {self.offset} more\n", style="dim")
        for index, item in enumerate(rows, start=self.offset):
            line = f"/{item.name.ljust(name_width)}  {item.description}"[:width]
            style = "reverse" if index == self.cursor else ""
            out.append(line, style=style)
            if index != end - 1:
                out.append("\n")
        remaining = len(self.items) - end
        if remaining > 0:
            out.append(f"\n↓ {remaining} more", style="dim")
        return out

    def _keep_visible(self) -> None:
        if self.cursor < self.offset:
            self.offset = self.cursor
        elif self.cursor >= self.offset + MAX_ROWS:
            self.offset = self.cursor - MAX_ROWS + 1
