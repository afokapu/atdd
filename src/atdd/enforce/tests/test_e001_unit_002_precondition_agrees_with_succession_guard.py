# URN: test:verify-enforcement:E001-UNIT-002-precondition-agrees-with-succession-guard
# Acceptance: acc:verify-enforcement:E001-UNIT-002-precondition-agrees-with-succession-guard
# WMBT: wmbt:verify-enforcement:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:verify-enforcement:E001-UNIT-002-precondition-agrees-with-succession-guard.

The retirement precondition this wagon PRODUCES is exactly the verdict the
govern-registry succession guard (#1427 E003) CONSUMES. Producer and consumer must
never disagree about whether a core node may be retired, so the two are driven over
one substrate and asserted to permit exactly the same deletions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.enforce.registry import CoreSuccessionError, guard_core_deletion
from atdd.enforce.succession import (
    SuccessionCoverageError,
    assert_succession_covered,
    retirement_precondition_holds,
    succession_coverage,
)

from .conftest import write_binding_lock, write_mirror_node

BOUND_CORE = "coder.dead-code.reachability"
UNBOUND_CORE = "tester.filename.urn"
UNTWINNED_CORE = "coach.template.no-duplicated-convention"  # no extension mirrors it


def _substrate(tmp_path: Path) -> Path:
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


def test_precondition_agrees_with_succession_guard(tmp_path: Path) -> None:
    _substrate(tmp_path)
    coverage = succession_coverage(tmp_path, path_b_blocking=True)

    # The precondition holds for the untwinned rule (no twin enforcement to lose)
    # and for the bound twin under a blocking Path B; it fails for the unbound twin.
    assert retirement_precondition_holds(UNTWINNED_CORE, coverage) is True
    assert retirement_precondition_holds(BOUND_CORE, coverage) is True
    assert retirement_precondition_holds(UNBOUND_CORE, coverage) is False

    # Asserting coverage raises, naming ONLY the rule that fails the precondition.
    with pytest.raises(SuccessionCoverageError) as exc:
        assert_succession_covered(
            [BOUND_CORE, UNBOUND_CORE, UNTWINNED_CORE], tmp_path, path_b_blocking=True
        )
    message = str(exc.value)
    assert UNBOUND_CORE in message
    assert BOUND_CORE not in message

    # ...and the CONSUMER (the govern-registry guard) permits EXACTLY the deletions
    # the precondition allows — producer and consumer agree.
    guard_core_deletion([BOUND_CORE, UNTWINNED_CORE], tmp_path, path_b_blocking=True)
    with pytest.raises(CoreSuccessionError):
        guard_core_deletion([UNBOUND_CORE], tmp_path, path_b_blocking=True)


def test_precondition_and_guard_agree_under_advisory_path_b(tmp_path: Path) -> None:
    _substrate(tmp_path)
    coverage = succession_coverage(tmp_path, path_b_blocking=False)

    # Under the advisory Path B CI actually runs, the bound twin stops being safe —
    # and the guard refuses that same deletion.
    assert retirement_precondition_holds(BOUND_CORE, coverage) is False
    with pytest.raises(CoreSuccessionError):
        guard_core_deletion([BOUND_CORE], tmp_path, path_b_blocking=False)

    # An untwinned rule stays retirable either way: nothing mirrors it, nothing is lost.
    assert retirement_precondition_holds(UNTWINNED_CORE, coverage) is True
    guard_core_deletion([UNTWINNED_CORE], tmp_path, path_b_blocking=False)
