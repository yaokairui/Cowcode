from __future__ import annotations

from cowcode.permission import Decision, RuleSet, parse_rule


def _rule(text: str):
    rule, err = parse_rule(text)
    assert err is None
    assert rule is not None
    return rule


def test_parse_rule_exact_match() -> None:
    rules = RuleSet(allow=[_rule("Bash(=git status)")])

    assert rules.match("Bash", "git status") == (Decision.ALLOW, True)
    assert rules.match("Bash", "git status -s") == (Decision.ALLOW, False)


def test_parse_rule_regex_match() -> None:
    rules = RuleSet(allow=[_rule("Bash(~^npm.*)")])

    assert rules.match("Bash", "npm install") == (Decision.ALLOW, True)
    assert rules.match("Bash", "pnpm install") == (Decision.ALLOW, False)


def test_parse_rule_not_regex_match() -> None:
    rules = RuleSet(allow=[_rule("Bash(!~^rm)")])

    assert rules.match("Bash", "ls -lh") == (Decision.ALLOW, True)
    assert rules.match("Bash", "rm -rf .") == (Decision.ALLOW, False)


def test_parse_rule_glob_backwards_compatible() -> None:
    rules = RuleSet(allow=[_rule("Write(**/*.py)")])

    assert rules.match("Write", "src/app.py") == (Decision.ALLOW, True)
    assert rules.match("Write", "src/app.txt") == (Decision.ALLOW, False)


def test_parse_rule_all_tool_calls_when_pattern_empty() -> None:
    rules = RuleSet(allow=[_rule("Read")])

    assert rules.match("Read", "anything") == (Decision.ALLOW, True)


def test_parse_rule_reports_invalid_regex() -> None:
    rule, err = parse_rule("Bash(~[invalid)")

    assert rule is None
    assert err
