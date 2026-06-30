# URN: test:author-plan-substrate:author-interlocking:E007-INTEGRATION-001-real-confirm-gate-zero-rows
# Acceptance: acc:author-plan-substrate:E007-INTEGRATION-001-real-confirm-gate-zero-rows
# WMBT: wmbt:author-plan-substrate:E007
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E007-INTEGRATION-001 — THE ANCHOR.

An interlocking authored by ``create_interlocking`` and attached to a kept train
unit satisfies the REAL #1249 Confirm gate end-to-end: the gate body
``assert_kept_train_interlocking_sanity`` returns without raising, and both
``sanity.interlocking_violations`` and ``validate_interlocking`` return 0 rows.
A direct-train-only plan is a no-op for authoring and still passes. A deliberately
mis-stamped route digest makes the gate FAIL — proving the digest is load-bearing.

This drives the gate's own recompute, not re-asserted digests.

RED: create_interlocking does not exist yet.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.planner.commands.author import create_interlocking
from atdd.planner.commands.confirm_interlocking import (
    assert_kept_train_interlocking_sanity,
)
from atdd.planner.commands.plan_session import PlanSession, SessionGateError, Step
from atdd.planner.commands.tests._il_author_fixtures import (
    ROUTE_ID,
    anchor_spec,
    author_route_train,
    kept_train_unit,
)
from atdd.planner.interlocking import (
    load_interlocking,
    sanity,
    validate_interlocking,
)


def _session_with(units, *, step=Step.CONFIRM.value, issue_ref="local:1265"):
    s = PlanSession(session_id="anchor-sess")
    s.step = step
    s.issue_ref = issue_ref
    s.units = units
    return s


def test_authored_interlocking_satisfies_real_gate_zero_rows(tmp_path):
    author_route_train(tmp_path)
    il_path = create_interlocking(anchor_spec(), root=tmp_path)

    # The artifact is schema-valid and loadable (#1248 loader hard-requires digests).
    il = load_interlocking(il_path)

    # The three gate surfaces named in AC-2 all return 0 rows.
    assert sanity.interlocking_violations(il, tmp_path) == {}
    assert validate_interlocking(il, tmp_path) == []

    session = _session_with([kept_train_unit()])
    # The REAL gate body returns silently (no raise == 0 evidence rows).
    assert assert_kept_train_interlocking_sanity(session, tmp_path) is None

    # And the full Confirm transition locks the session.
    session.confirm(tmp_path)
    assert session.locked is True


def test_direct_train_only_plan_is_noop_and_confirms(tmp_path):
    # A kept train unit with NO interlocking reference: authoring is a no-op and
    # the gate passes (direct trains are allowed).
    author_route_train(tmp_path)
    direct_unit = {"ref": "train:0001-anchor-nominal", "kind": "train",
                   "verdict": "keep", "spec": {}}
    session = _session_with([direct_unit])
    assert assert_kept_train_interlocking_sanity(session, tmp_path) is None
    session.confirm(tmp_path)
    assert session.locked is True


def test_mis_stamped_digest_makes_gate_fail(tmp_path):
    author_route_train(tmp_path)
    il_path = create_interlocking(anchor_spec(), root=tmp_path)

    # Corrupt the load-bearing route projection digest on disk.
    doc = yaml.safe_load(il_path.read_text(encoding="utf-8"))
    doc["routes"][0]["projection"]["expected_sequence_digest"] = "deadbeef" * 8
    il_path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

    # Sanity now reports the projection-equivalence row...
    il = load_interlocking(il_path)
    rows = sanity.interlocking_violations(il, tmp_path)
    assert "planner.train.interlocking-projection-equivalence" in rows

    # ...and the real Confirm gate fails closed.
    session = _session_with([kept_train_unit()])
    with pytest.raises(SessionGateError):
        assert_kept_train_interlocking_sanity(session, tmp_path)
