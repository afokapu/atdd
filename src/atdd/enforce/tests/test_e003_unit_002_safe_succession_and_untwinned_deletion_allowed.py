# URN: test:govern-registry:E003-UNIT-002-safe-succession-and-untwinned-deletion-allowed
# Acceptance: acc:govern-registry:E003-UNIT-002-safe-succession-and-untwinned-deletion-allowed
# WMBT: wmbt:govern-registry:E003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E003-UNIT-002-safe-succession-and-untwinned-deletion-allowed.

Deletion is permitted only when succession is genuinely safe — the twin is bound
AND Path B is blocking — or when no extension twin mirrors the rule at all; a twin
that is not bound never makes deletion safe.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.enforce.registry import CoreSuccessionError, guard_core_deletion

from .conftest import write_binding_lock, write_mirror_node


def _bound(convention_id: str) -> dict:
    return {
        "convention_id": convention_id,
        "disposition": "bound",
        "implementation_id": convention_id,
        "workspace_id": "atdd.workspace.python-pytest",
        "contract_version": "1.0.0",
    }


def test_bound_and_blocking_twin_permits_deletion(tmp_path: Path) -> None:
    core_rule = "coder.dead-code.reachability"
    write_mirror_node(tmp_path, rule_id=core_rule, legacy_rule_id=core_rule)
    write_binding_lock(tmp_path, [_bound(core_rule)])

    # Twin bound AND Path B blocking → succession is safe, no raise.
    assert guard_core_deletion([core_rule], tmp_path, path_b_blocking=True) is None


def test_untwinned_rule_deletion_is_allowed(tmp_path: Path) -> None:
    # A core rule that no extension node mirrors — nothing to lose.
    write_mirror_node(
        tmp_path,
        rule_id="coder.other.mirrored",
        legacy_rule_id="coder.other.mirrored",
    )
    write_binding_lock(tmp_path, [_bound("coder.other.mirrored")])

    assert (
        guard_core_deletion(
            ["coder.security.sql-injection"], tmp_path, path_b_blocking=False
        )
        is None
    )


def test_unbound_twin_is_refused_even_when_path_b_blocks(tmp_path: Path) -> None:
    core_rule = "coder.dead-code.reachability"
    # Twin exists but is NOT bound in the lock.
    write_mirror_node(tmp_path, rule_id=core_rule, legacy_rule_id=core_rule)
    write_binding_lock(tmp_path, [])

    with pytest.raises(CoreSuccessionError) as exc:
        guard_core_deletion([core_rule], tmp_path, path_b_blocking=True)
    assert "not bound" in str(exc.value)
