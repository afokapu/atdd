# URN: test:govern-providers:E004-UNIT-002-unknown-rule-selection-refuses
# Acceptance: acc:govern-providers:E004-UNIT-002-unknown-rule-selection-refuses
# WMBT: wmbt:govern-providers:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED Test for acc:govern-providers:E004-UNIT-002-unknown-rule-selection-refuses.

A selection naming a rule no bound convention declares must RAISE, not resolve to an
empty set. An empty set runs no detector, and a run that spawns no detector reports
clean — so a mistyped rule id would silently turn a gate into a rubber stamp. This is
the same fail-closed principle the runner already applies to a crashed provider.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.enforce.runner import EnforceUsageError, _bound_conventions

from .conftest import write_binding_lock


def _entry(convention_id: str) -> dict:
    return {
        "convention_id": convention_id,
        "disposition": "bound",
        "implementation_id": convention_id,
        "workspace_id": "atdd.workspace.python-pytest",
        "contract_version": "1.1.0",
    }


def test_e004_unit_002_unknown_rule_selection_refuses(tmp_path: Path):
    write_binding_lock(tmp_path, [_entry("coder.demo.alpha"), _entry("coder.demo.beta")])

    with pytest.raises(EnforceUsageError) as excinfo:
        _bound_conventions(tmp_path, rules={"coder.demo.alpha", "coder.demo.typo"})

    # The error names the offending id, so the caller can fix the typo ...
    assert "coder.demo.typo" in str(excinfo.value)
    # ... and does not name the rule that WAS resolvable.
    assert "coder.demo.beta" not in str(excinfo.value)


def test_e004_unit_002_unknown_rule_selection_refuses_even_when_lock_is_empty(tmp_path: Path):
    """An empty lock is the sharpest case: every selection is unknown, and today's
    code path returns ``[]`` — the exact silent-clean this acceptance forbids."""
    write_binding_lock(tmp_path, [])

    with pytest.raises(EnforceUsageError):
        _bound_conventions(tmp_path, rules={"coder.demo.alpha"})
