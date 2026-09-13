# URN: test:govern-lifecycle:define-transition-autonomy:C027-UNIT-001-the-node-states-what-the-runtime-does
# Acceptance: acc:govern-lifecycle:C027-UNIT-001-the-node-states-what-the-runtime-does
# WMBT: wmbt:govern-lifecycle:C027
# Phase: GREEN
# Layer: unit
# Assertion: structural
"""C027-UNIT-001 — the node stops claiming the autonomy key binds no behaviour.

#1626 authored the node "declarative first", and said so in three places: the
statement's blast-radius clause, the rationale's "nothing reads the key yet", and
`metadata.disposition: documentation-only`. #1798 then made `ApprovalTokenGateCheck`
waive a live gate on the key, and edited none of them.

All three are asserted here, plus the `terms` block, because
`legality_stays_with_atdd` restates the same claim in its own words — a fix that
edited only `statement` would leave the false assertion standing one field over.
"""
from __future__ import annotations

import pytest

from ._c027_autonomy_claim import (
    DOCUMENTATION_ONLY,
    INERTNESS_CLAIMS,
    claims_key_is_unread,
    load_node,
    node_prose,
)
from ._d020_autonomy import NODE_REL

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach, pytest.mark.platform]


def _node():
    return load_node(find_repo_root() / NODE_REL)


@pytest.mark.platform
def test_no_field_claims_the_key_is_unread() -> None:
    """No inertness phrase survives anywhere in the node's prose."""
    prose = node_prose(_node())
    found = [claim for claim in INERTNESS_CLAIMS if claim in prose]
    assert not found, (
        f"the node still asserts the autonomy key binds no behaviour: {found!r}. "
        f"ApprovalTokenGateCheck._autonomy_waiver has read it since #1798, and a "
        f"permissive declaration now LIFTS an operator stop rather than producing a "
        f"command ATDD rejects — the stated blast radius is inverted, not merely stale."
    )


@pytest.mark.platform
def test_the_node_names_the_gate_that_reads_the_key() -> None:
    """A reader learns WHERE the consumption lives, not merely that it exists."""
    prose = node_prose(_node())
    assert "approvaltokengatecheck" in prose.replace(" ", "") or "approval gate" in prose, (
        "the node does not name the runtime that reads `autonomy`. Saying the key "
        "is read without saying by what leaves the reader no better placed to judge "
        "the blast radius than the false claim did."
    )


@pytest.mark.platform
def test_disposition_is_no_longer_documentation_only() -> None:
    """The node binds behaviour, so it must not declare that it binds none."""
    disposition = ((_node().get("metadata") or {}).get("disposition") or "").strip()
    assert disposition != DOCUMENTATION_ONLY, (
        f"metadata.disposition is still {DOCUMENTATION_ONLY!r}, which declares the "
        f"node binds no validator. C027 binds one, and the gate already reads the key."
    )


@pytest.mark.platform
def test_the_claim_reader_agrees_with_the_three_assertions_above() -> None:
    """The helper the guard uses reaches the same verdict as the explicit checks.

    Pins the reader to the assertions rather than letting it drift into agreeing
    with a node nobody fixed — the guard is only as good as what it reads.
    """
    assert not claims_key_is_unread(_node()), (
        "claims_key_is_unread() still reports the node as claiming inertness while "
        "the explicit assertions above expect it corrected; the reader and the "
        "acceptance disagree, which makes the guard untrustworthy either way."
    )
