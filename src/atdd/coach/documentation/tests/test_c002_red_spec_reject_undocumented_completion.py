# URN: test:govern-documentation-obligation:reject-undocumented-completion:C002-RED-SPEC
# Acceptance: acc:govern-documentation-obligation:C002-UNIT-001-red-declared-change-absent-blocks-complete
# Acceptance: acc:govern-documentation-obligation:C002-SMOKE-001-live-complete-refuses-unresolved-obligation
# WMBT: wmbt:govern-documentation-obligation:C002
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED spec for wmbt:govern-documentation-obligation:C002 — owned by #1828.

COMPLETE runs integrity first, then delegates, then refuses an unresolved or unobservable obligation.

Every assertion below fails today: the behaviour is unimplemented and #1828 is the
issue that implements it. These live here rather than beside their eventual code
because that code does not exist yet; each moves to its implementation package when
#1828 lands.

They exist now because #1789 authored these acceptances, and an acceptance no test
names is an obligation no gate can ask for —
tester.acceptance-violation.validator-binding-must-be-bidirectional, strict.
"""
from __future__ import annotations

import pytest


def test_unit_001_red_declared_change_absent_blocks_complete() -> None:
    """AC-UNIT-001 (RED) — The transition is refused naming the undischarged artifact

    Given: An issue declaring a documentation change whose artifact is absent from the branch diff
    When:  the COMPLETE transition is attempted
    """
    pytest.fail(
        "unimplemented: #1828 owns C002-UNIT-001-red-declared-change-absent-blocks-complete"
    )


def test_smoke_001_live_complete_refuses_unresolved_obligation() -> None:
    """AC-SMOKE-001 (SMOKE) — The command exits non-zero and names the documentation obligation

    Given: A real issue at REFACTOR with an unresolved declared documentation obligation
    When:  atdd coach transition to COMPLETE is run
    """
    pytest.fail(
        "unimplemented: #1828 owns C002-SMOKE-001-live-complete-refuses-unresolved-obligation"
    )


