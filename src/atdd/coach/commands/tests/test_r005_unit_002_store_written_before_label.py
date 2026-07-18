# URN: test:govern-lifecycle:R005-UNIT-002-store-written-before-label
# Acceptance: acc:govern-lifecycle:R005-UNIT-002-store-written-before-label
# WMBT: wmbt:govern-lifecycle:R005
# Phase: RED
# Layer: application
# Assertion: behavioral
"""R005-UNIT-002 — ``IssueManager.update`` writes ``objects.state`` BEFORE it
projects the ``atdd:<PHASE>`` label.

The ordering is the fix, not a detail of it. ``atdd:<PHASE>`` is a rendering of
the store, so the source of truth has to move before the artifact derived from
it; write the label first and any failure in between leaves the projection
asserting a transition that never happened. That is the shape of all 236 drifted
records — a label ahead of a store that never earned it.

Both writes are instrumented on one recorder so the assertion is about their
*order*, which no single-call assertion can catch.

Issue #1452.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.issue import IssueManager

pytestmark = [pytest.mark.coach]


@pytest.fixture
def recorded(tmp_path):
    """Drive a successful update() and return (call order, label writes)."""
    order: list[str] = []
    labels: list[list[str]] = []

    client = MagicMock()
    client.add_label.side_effect = lambda n, ls: (
        order.append("label"),
        labels.append(list(ls)),
    )
    client.remove_label.side_effect = lambda n, ls: None

    manager = IssueManager(tmp_path)

    with patch.object(manager, "_check_initialized", return_value=True), \
         patch.object(
             manager,
             "_resolve_issue",
             return_value=(1452, {"labels": [{"name": "atdd:SMOKE"}], "body": ""}, client),
         ), \
         patch.object(manager, "_transition_gates_pass", return_value=True), \
         patch.object(manager, "_apply_text_updates", return_value=[]), \
         patch.object(
             manager,
             "_store_set_status",
             side_effect=lambda n, s: order.append("store") or True,
         ):
        rc = manager.update(issue_id="1452", status="REFACTOR")

    assert rc == 0, "The transition must succeed for the ordering to mean anything."
    return order, labels


def test_store_write_precedes_the_label_projection(recorded):
    """objects.state moves first; the label is rendered from it."""
    order, _ = recorded
    assert order.index("store") < order.index("label"), (
        "IssueManager.update projected the atdd:<PHASE> label before writing "
        f"objects.state (observed order: {order}). Store first, label as its "
        "projection — otherwise a failure between the two writes leaves an "
        "unearned label, which is exactly the 236-record drift signature."
    )


def test_both_writes_actually_happen(recorded):
    """Inverting the order must not drop either write."""
    order, _ = recorded
    assert "store" in order, "The store write did not happen at all."
    assert "label" in order, "The label projection did not happen at all."


def test_projected_label_is_the_target_phase(recorded):
    """The projection renders exactly the phase the store was set to."""
    _, labels = recorded
    flat = [item for sub in labels for item in sub]
    assert flat == ["atdd:REFACTOR"], (
        f"Expected the label projection to be exactly atdd:REFACTOR; got {flat}."
    )
