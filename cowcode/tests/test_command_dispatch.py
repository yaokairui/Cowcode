"""slash 输入解析测试。"""

from __future__ import annotations

import pytest

from cowcode.command import parse


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ("", False)),
        ("   ", ("", False)),
        ("hello", ("", False)),
        ("/", ("", True)),
        ("/help", ("help", True)),
        ("  /HELP  ", ("help", True)),
        ("/help xx", ("", True)),
        ("/help  ", ("help", True)),
        ("//double", ("", True)),
        ("/ /help", ("", True)),
    ],
)
def test_parse(text: str, expected: tuple[str, bool]) -> None:
    assert parse(text) == expected
