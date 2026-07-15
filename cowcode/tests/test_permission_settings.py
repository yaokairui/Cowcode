from __future__ import annotations

from cowcode.permission import PermissionsBlock, Settings
from cowcode.permission.settings import to_rule_set


def test_to_rule_set_reports_parse_error(capsys) -> None:
    settings = Settings(
        permissions=PermissionsBlock(
            allow=["Bash(=git status)", "Bash(~[invalid)"],
            deny=["Write(**/*.py)"],
        )
    )

    rule_set = to_rule_set(settings)

    captured = capsys.readouterr()
    assert len(rule_set.allow) == 1
    assert len(rule_set.deny) == 1
    assert "parse failed" in captured.err
    assert "Bash(~[invalid)" in captured.err
