"""配置文件加载、工具分类与目标提取。"""

from __future__ import annotations


import yaml

from cowcode.permission import PermissionsBlock, RuleSet, Settings, SettingsError


def load_settings(path: str) -> Settings:
    """加载单个 YAML 配置文件。文件不存在 → 空；解析失败 → 抛 SettingsError。"""
    from pathlib import Path as _Path

    if not _Path(path).exists():
        return Settings()
    try:
        raw = yaml.safe_load(_Path(path).read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SettingsError(f"Invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise SettingsError(f"Failed to read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SettingsError(f"Config root in {path} must be a mapping")
    default_mode = str(raw.get("default_mode", "") or "")
    perms_raw = raw.get("permissions")
    if isinstance(perms_raw, dict):
        block = PermissionsBlock(
            allow=_normalize_list(perms_raw.get("allow")),
            deny=_normalize_list(perms_raw.get("deny")),
        )
    else:
        block = PermissionsBlock()
    return Settings(default_mode=default_mode, permissions=block)


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if isinstance(v, str) and v.strip()]
    return []


def to_rule_set(settings: Settings) -> RuleSet:
    """把配置转向 RuleSet，跳过非法条目。"""
    from cowcode.permission import _parse_rule

    rule_set = RuleSet()
    for text in settings.permissions.allow:
        rule, ok = _parse_rule(text)
        if ok and rule.tool:
            rule_set.allow.append(rule)
    for text in settings.permissions.deny:
        rule, ok = _parse_rule(text)
        if ok and rule.tool:
            rule.allow = False
            rule_set.deny.append(rule)
    return rule_set


def default_rules() -> RuleSet:
    """返回空规则集。"""
    return RuleSet(allow=[], deny=[])
