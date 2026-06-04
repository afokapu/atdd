# Acceptance: acc:govern-lifecycle:C006-UNIT-001-override-cannot-remove-commons-floor
# Acceptance: acc:govern-lifecycle:C006-UNIT-002-defaults-contain-commons-floor
# Acceptance: acc:govern-lifecycle:C006-SMOKE-001-repo-config-keeps-commons-floor
"""planner.theme.theme-zero-mandatory validator (issue #970).

Theme digit 0 (commons) is the mandatory, non-removable floor of every resolved
theme set. A consumer ``.atdd/config.yaml`` ``themes:`` block may add or override
themes 1-9, but it MUST NOT remove digit 0 nor rename it away from the locked
token ``commons``. The resolver pins digit 0 regardless of override input, so any
resolved theme map always contains ``commons`` at digit 0.

Rule: planner.theme.theme-zero-mandatory (severity 4, block)
Convention: src/atdd/planner/conventions/theme.convention.yaml::rules
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

from ._theme_taxonomy import (
    CANONICAL_THEME_0,
    check_theme_zero_mandatory,
    resolve_theme_set,
)

pytestmark = [pytest.mark.planner]

_RULE_ID = "planner.theme.theme-zero-mandatory"
_RULE = bind_rule(_RULE_ID)

REPO_ROOT = find_repo_root()


def _load_repo_config() -> dict:
    import yaml

    cfg_path = REPO_ROOT / ".atdd" / "config.yaml"
    if not cfg_path.exists():
        return {}
    return yaml.safe_load(cfg_path.read_text()) or {}


def test_commons_is_always_in_resolved_theme_set() -> None:
    """Repo config (and bare defaults) always resolve commons at digit 0."""
    violations = check_theme_zero_mandatory(_load_repo_config())
    assert violations == [], (
        f"[{_RULE_ID}] commons floor missing from resolved theme set:\n"
        + "\n".join(f"  - {v.detail}" for v in violations)
    )


def test_override_cannot_remove_commons_floor() -> None:
    """An override that renames/removes digit 0 still resolves to commons."""
    hostile = {"themes": {"0": "platform", "1": "qualification"}}
    resolved = resolve_theme_set(hostile)
    assert resolved.get("0") == CANONICAL_THEME_0, (
        "digit-0 override must be ignored; commons is the non-removable floor"
    )
    assert CANONICAL_THEME_0 in resolved.values()


def test_defaults_contain_commons_floor() -> None:
    """With no config, the resolved set still pins commons at digit 0."""
    resolved = resolve_theme_set(None)
    assert resolved.get("0") == CANONICAL_THEME_0
    assert check_theme_zero_mandatory(None) == []
