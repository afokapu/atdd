# URN: test:spawn-agents:E027-UNIT-001-session-convention-declares-wagon-graph-rule
# Acceptance: acc:spawn-agents:E027-UNIT-001-session-convention-declares-wagon-graph-rule
# WMBT: wmbt:spawn-agents:E027
# Phase: RED
# Layer: unit
"""E027-UNIT-001 — src/atdd/coach/conventions/session.convention.yaml declares
a rule whose id is 'coach.launch-prompt.must-include-wagon-graph' with
severity 3 and suppress_mode 'suppress-and-clean'.

Phase RED: fails because the rule has not been added to session.convention.yaml
yet (assert fails on text search + bind_rule raises RuleNotInRegistryError).
Phase GREEN: rule exists with correct fields; bind_rule() resolves cleanly.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.spawn_agents]

_CONVENTION_PATH = Path("src/atdd/coach/conventions/session.convention.yaml")
_RULE_ID = "coach.launch-prompt.must-include-wagon-graph"
_EXPECTED_SEVERITY = 3
_EXPECTED_SUPPRESS_MODE = "suppress-and-clean"


def _load_convention() -> dict:
    assert _CONVENTION_PATH.exists(), f"Convention file not found: {_CONVENTION_PATH}"
    return yaml.safe_load(_CONVENTION_PATH.read_text(encoding="utf-8")) or {}


def _find_rule(data: dict, rule_id: str) -> dict | None:
    """Return the rule dict for *rule_id* from any 'rules' list in the convention."""
    for key, value in data.items():
        if key == "rules" and isinstance(value, list):
            for rule in value:
                if isinstance(rule, dict) and rule.get("id") == rule_id:
                    return rule
    # Nested sections (e.g. spawn_time.rules)
    for value in data.values():
        if isinstance(value, dict):
            result = _find_rule(value, rule_id)
            if result is not None:
                return result
    return None


def test_convention_file_contains_rule_id() -> None:
    """Rule ID 'coach.launch-prompt.must-include-wagon-graph' must appear in session.convention.yaml."""
    text = _CONVENTION_PATH.read_text(encoding="utf-8") if _CONVENTION_PATH.exists() else ""
    assert _RULE_ID in text, (
        f"Rule '{_RULE_ID}' not found in {_CONVENTION_PATH}. "
        "E027: add the rule under the 'rules:' section with "
        "severity: 3 and suppress_mode: suppress-and-clean."
    )


def test_rule_has_correct_severity() -> None:
    """Rule severity must be 3."""
    data = _load_convention()
    rule = _find_rule(data, _RULE_ID)
    assert rule is not None, (
        f"Rule '{_RULE_ID}' not found in parsed convention data. "
        "E027: add the rule to session.convention.yaml."
    )
    assert rule.get("severity") == _EXPECTED_SEVERITY, (
        f"Expected severity {_EXPECTED_SEVERITY}, got {rule.get('severity')!r}. "
        "E027: set severity: 3 on the coach.launch-prompt.must-include-wagon-graph rule."
    )


def test_rule_has_correct_suppress_mode() -> None:
    """Rule suppress_mode must be 'suppress-and-clean'."""
    data = _load_convention()
    rule = _find_rule(data, _RULE_ID)
    assert rule is not None, (
        f"Rule '{_RULE_ID}' not found in parsed convention data."
    )
    assert rule.get("suppress_mode") == _EXPECTED_SUPPRESS_MODE, (
        f"Expected suppress_mode '{_EXPECTED_SUPPRESS_MODE}', "
        f"got {rule.get('suppress_mode')!r}. "
        "E027: set suppress_mode: suppress-and-clean."
    )


def test_rule_description_references_wagon_graph_or_e022_e023() -> None:
    """Rule description must reference the wagon-graph section or E025/E026."""
    data = _load_convention()
    rule = _find_rule(data, _RULE_ID)
    assert rule is not None, f"Rule '{_RULE_ID}' not found in parsed convention data."
    desc = (rule.get("description") or rule.get("detail") or "").lower()
    assert any(kw in desc for kw in ("wagon", "e022", "e023", "graph")), (
        "Rule description must reference 'wagon', 'E025', 'E026', or 'graph'. "
        f"Got description: {rule.get('description') or rule.get('detail')!r}. "
        "E027: the description must explain why the rule exists."
    )


def test_bind_rule_resolves_wagon_graph_rule() -> None:
    """bind_rule('coach.launch-prompt.must-include-wagon-graph') must resolve without error."""
    from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule

    try:
        rule = bind_rule(_RULE_ID)
    except RuleNotInRegistryError as exc:
        pytest.fail(
            f"bind_rule('{_RULE_ID}') raised RuleNotInRegistryError: {exc}. "
            "E027: add the rule to session.convention.yaml so bind_rule() can find it."
        )
    assert rule.rule_id == _RULE_ID, f"Expected rule_id {_RULE_ID!r}, got {rule.rule_id!r}"
    assert rule.severity == _EXPECTED_SEVERITY, (
        f"Expected severity {_EXPECTED_SEVERITY}, got {rule.severity}"
    )
