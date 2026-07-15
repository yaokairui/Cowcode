from __future__ import annotations

import pytest

from cowcode.permission.matcher import compile_matcher


@pytest.mark.parametrize(
    ("pattern", "target", "expected", "is_command"),
    [
        pytest.param("=git status", "git status", True, True, id="exact-hit"),
        pytest.param("=git status", "git status -s", False, True, id="exact-miss"),
        pytest.param(
            "~^npm (install|test)$", "npm install", True, True, id="regex-hit"
        ),
        pytest.param(
            "~^npm (install|test)$", "npm run dev", False, True, id="regex-miss"
        ),
        pytest.param("!=foo", "foo", False, False, id="not-exact-miss"),
        pytest.param("!=foo", "bar", True, False, id="not-exact-hit"),
        pytest.param("!~^rm", "ls -lh", True, True, id="not-regex-hit"),
        pytest.param("!~^rm", "rm -rf .", False, True, id="not-regex-miss"),
        pytest.param("!git *", "npm install", True, True, id="not-glob-hit"),
        pytest.param("!git *", "git status", False, True, id="not-glob-miss"),
        pytest.param("**/*.py", "src/cowcode/app.py", True, False, id="path-glob-hit"),
        pytest.param(
            "**/*.py", "src/cowcode/app.txt", False, False, id="path-glob-miss"
        ),
    ],
)
def test_compile_matcher_types(
    pattern: str, target: str, expected: bool, is_command: bool
) -> None:
    matcher = compile_matcher(pattern, is_command=is_command)

    assert matcher.match(target) is expected


def test_compile_matcher_invalid_regex() -> None:
    with pytest.raises(ValueError):
        compile_matcher("~[invalid", is_command=True)


def test_compile_matcher_empty_pattern() -> None:
    with pytest.raises(ValueError):
        compile_matcher("", is_command=False)


def test_exact_matcher_string_roundtrip() -> None:
    assert str(compile_matcher("=foo", is_command=False)) == "=foo"
