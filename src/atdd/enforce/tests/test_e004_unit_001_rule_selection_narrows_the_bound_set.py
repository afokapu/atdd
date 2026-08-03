# URN: test:govern-providers:E004-UNIT-001-rule-selection-narrows-the-bound-set
# Acceptance: acc:govern-providers:E004-UNIT-001-rule-selection-narrows-the-bound-set
# WMBT: wmbt:govern-providers:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED Test for acc:govern-providers:E004-UNIT-001-rule-selection-narrows-the-bound-set.

Naming a subset of the bound rules resolves to exactly those entries. Without this,
``enforce`` fans out to every ``bound`` convention — 62 in the toolkit's own lock —
and each one costs a provider subprocess, so a caller that needs one rule's verdict
pays for the whole set.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.runner import _bound_conventions

from .conftest import write_binding_lock


def _entry(convention_id: str, disposition: str = "bound") -> dict:
    return {
        "convention_id": convention_id,
        "disposition": disposition,
        "implementation_id": convention_id,
        "workspace_id": "atdd.workspace.python-pytest",
        "contract_version": "1.1.0",
    }


def test_e004_unit_001_rule_selection_narrows_the_bound_set(tmp_path: Path):
    write_binding_lock(
        tmp_path,
        [
            _entry("coder.demo.alpha"),
            _entry("coder.demo.beta"),
            _entry("coder.demo.gamma"),
            _entry("coder.demo.unbound", disposition="advisory"),
        ],
    )

    selected = _bound_conventions(tmp_path, rules={"coder.demo.alpha", "coder.demo.gamma"})

    assert [c["convention_id"] for c in selected] == ["coder.demo.alpha", "coder.demo.gamma"]
    # The un-named bound rule is excluded, so its provider is never spawned ...
    assert not any(c["convention_id"] == "coder.demo.beta" for c in selected)
    # ... and selection never promotes a non-bound disposition.
    assert not any(c["convention_id"] == "coder.demo.unbound" for c in selected)
