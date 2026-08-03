# URN: test:govern-providers:E004-UNIT-003-no-selection-enforces-every-bound-rule
# Acceptance: acc:govern-providers:E004-UNIT-003-no-selection-enforces-every-bound-rule
# WMBT: wmbt:govern-providers:E004
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED Test for acc:govern-providers:E004-UNIT-003-no-selection-enforces-every-bound-rule.

Omitting the selection preserves the whole-bound-set behaviour. Rule selection is an
ADDITIVE seam: `atdd enforce` with no `--rule`, the post-commit hook, and CI all keep
running every bound convention exactly as before.
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


def test_e004_unit_003_no_selection_enforces_every_bound_rule(tmp_path: Path):
    write_binding_lock(
        tmp_path,
        [
            _entry("coder.demo.alpha"),
            _entry("coder.demo.beta"),
            _entry("coder.demo.gamma"),
            _entry("coder.demo.unbound", disposition="advisory"),
        ],
    )

    every = _bound_conventions(tmp_path)

    assert [c["convention_id"] for c in every] == [
        "coder.demo.alpha",
        "coder.demo.beta",
        "coder.demo.gamma",
    ]
    # An explicit None is the same as omitting it — no caller has to pass a sentinel.
    assert _bound_conventions(tmp_path, rules=None) == every
