from __future__ import annotations

from cowcode.permission.sandbox import sandbox_ok


def test_sandbox_allows_tmp_but_rejects_etc(tmp_path) -> None:
    root = str(tmp_path.resolve())
    assert sandbox_ok(root, "/tmp/foo.txt") is True
    assert sandbox_ok(root, "/private/tmp/foo.txt") is True
    assert sandbox_ok(root, "/etc/passwd") is False
