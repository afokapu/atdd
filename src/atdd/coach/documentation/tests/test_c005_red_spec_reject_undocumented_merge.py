# URN: test:enforce-merge-authority:reject-undocumented-merge:C005-RED-SPEC
# Acceptance: acc:enforce-merge-authority:C005-UNIT-001-red-unresolved-obligation-blocks-merge
# Acceptance: acc:enforce-merge-authority:C005-UNIT-002-lookup-failure-fails-closed
# Acceptance: acc:enforce-merge-authority:C005-SMOKE-001-real-merge-check-refuses-an-unresolved-obligation
# WMBT: wmbt:enforce-merge-authority:C005
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED spec for wmbt:enforce-merge-authority:C005 — owned by #1829.

Merge preserves the COMPLETE invariant and fails closed when the obligation lookup cannot be performed.

Every assertion below fails today: the behaviour is unimplemented and #1829 is the
issue that implements it. These live here rather than beside their eventual code
because that code does not exist yet; each moves to its implementation package when
#1829 lands.

They exist now because #1789 authored these acceptances, and an acceptance no test
names is an obligation no gate can ask for —
tester.acceptance-violation.validator-binding-must-be-bidirectional, strict.
"""
from __future__ import annotations

import pytest


def test_unit_001_red_unresolved_obligation_blocks_merge() -> None:
    """AC-UNIT-001 (RED) — The merge is blocked naming the obligation

    Given: A pull request whose issue carries an unresolved declared documentation obligation
    When:  the merge check runs
    """
    pytest.fail(
        "unimplemented: #1829 owns C005-UNIT-001-red-unresolved-obligation-blocks-merge"
    )


def test_unit_002_lookup_failure_fails_closed() -> None:
    """AC-UNIT-002 (GREEN) — The check blocks rather than passing

    Given: A merge check whose obligation lookup cannot be performed
    When:  the merge check runs
    """
    pytest.fail(
        "unimplemented: #1829 owns C005-UNIT-002-lookup-failure-fails-closed"
    )


def test_smoke_001_real_merge_check_refuses_an_unresolved_obligation() -> None:
    """AC-SMOKE-001 (SMOKE) — Entry to main is refused and the obligation is named

    Given: A real branch whose issue carries an unresolved declared documentation obligation
    When:  the real merge check runs against it
    """
    pytest.fail(
        "unimplemented: #1829 owns C005-SMOKE-001-real-merge-check-refuses-an-unresolved-obliga"
    )


