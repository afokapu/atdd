# URN: test:verify-enforcement:E001-UNIT-001-proof-marks-retirement-safe-only-when-twin-bound-and-blocking
# Acceptance: acc:verify-enforcement:E001-UNIT-001-proof-marks-retirement-safe-only-when-twin-bound-and-blocking
# WMBT: wmbt:verify-enforcement:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:verify-enforcement:E001-UNIT-001-proof-marks-retirement-safe-only-when-twin-bound-and-blocking.

The proof emits one succession-coverage record per core rule an extension mirrors,
and marks retirement safe ONLY when the twin is bound AND Path B is blocking. A
bound twin under an advisory Path B, and an unbound twin under a blocking Path B,
are both unsafe — both conditions are required.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.succession import succession_coverage

from .conftest import write_binding_lock, write_mirror_node

BOUND_CORE = "coder.dead-code.reachability"
UNBOUND_CORE = "tester.filename.urn"


def _substrate(tmp_path: Path) -> Path:
    """Two extension nodes mirroring two distinct core rules; only one is bound."""
    write_mirror_node(tmp_path, rule_id="ext.bound.twin", legacy_rule_id=BOUND_CORE)
    write_mirror_node(tmp_path, rule_id="ext.unbound.twin", legacy_rule_id=UNBOUND_CORE)
    write_binding_lock(
        tmp_path,
        [
            {
                "convention_id": "ext.bound.twin",
                "disposition": "bound",
                "implementation_id": "ext.bound.twin",
                "workspace_id": "atdd.workspace.python-pytest",
                "contract_version": "1.0.0",
            }
        ],
    )
    return tmp_path


def test_proof_marks_retirement_safe_only_when_twin_bound_and_blocking(tmp_path: Path) -> None:
    _substrate(tmp_path)

    # One record per MIRRORED core rule, keyed by the CORE rule_id the twin mirrors.
    blocking = {c.rule_id: c for c in succession_coverage(tmp_path, path_b_blocking=True)}
    assert set(blocking) == {BOUND_CORE, UNBOUND_CORE}

    # The record conforms to the commons:succession-coverage contract.
    assert blocking[BOUND_CORE].as_payload() == {
        "rule_id": BOUND_CORE,
        "disposition": "strict",
    }

    # Under a BLOCKING Path B only the BOUND twin makes its core rule retirement-safe.
    assert blocking[BOUND_CORE].retirement_safe is True
    assert blocking[UNBOUND_CORE].retirement_safe is False
    assert blocking[UNBOUND_CORE].twin_bound is False

    # Under the ADVISORY Path B that CI actually runs, NOTHING is retirement-safe —
    # not even the bound twin. Bound is necessary but not sufficient.
    advisory = {c.rule_id: c for c in succession_coverage(tmp_path, path_b_blocking=False)}
    assert advisory[BOUND_CORE].twin_bound is True
    assert advisory[BOUND_CORE].retirement_safe is False
    assert advisory[UNBOUND_CORE].retirement_safe is False
