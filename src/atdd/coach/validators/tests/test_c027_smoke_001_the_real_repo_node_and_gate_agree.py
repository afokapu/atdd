# URN: test:govern-lifecycle:define-transition-autonomy:C027-SMOKE-001-the-real-repo-node-and-gate-agree
# Acceptance: acc:govern-lifecycle:C027-SMOKE-001-the-real-repo-node-and-gate-agree
# WMBT: wmbt:govern-lifecycle:C027
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C027-SMOKE-001 — the repository's own committed node and gate agree.

Against the committed artifacts, not fixtures: C027-UNIT-002 proves the guard can
catch drift in a fabricated pair, and this proves the shipped pair is not drifted.
A guard that is only ever exercised on fixtures has never been asked about the
thing it exists to watch.

The two guardrails below are what keep this issue honest about its scope: #1798's
waiver must still fire, and the one operator judgement gate must still refuse. If
correcting the prose had quietly changed either, this file says so.
"""
from __future__ import annotations

import pytest

from ._c027_autonomy_claim import gate_reads_autonomy, load_node, resolve_claim
from ._d020_autonomy import NODE_REL

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

pytestmark = [pytest.mark.coach, pytest.mark.platform]


@pytest.mark.platform
def test_the_committed_node_and_gate_agree() -> None:
    """The shipped pair is consistent."""
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; the committed node is the subject")

    verdict = resolve_claim(load_node(find_repo_root() / NODE_REL))
    assert verdict, verdict.detail


@pytest.mark.platform
def test_the_waiver_1798_shipped_still_fires() -> None:
    """This issue removes no behaviour #1798 added.

    `gate_reads_autonomy` is true only when an `autonomy: agent` edge is waived
    AND an `operator` edge is still refused, so one assertion covers both halves:
    the waiver fires, and it did not become unconditional.
    """
    if not is_atdd_source_repo():
        pytest.skip("toolkit-self acceptance; the committed gate is the subject")

    assert gate_reads_autonomy(), (
        "the committed approval check no longer waives on `autonomy: agent` while "
        "still refusing an operator edge. C027 corrects the node's description of "
        "#1798; it must not alter #1798, and it must not make the gate waive "
        "everything."
    )
