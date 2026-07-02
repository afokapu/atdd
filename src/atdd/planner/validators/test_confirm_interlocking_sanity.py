# URN: component:atdd-plan-core:confirm-gate:ConfirmInterlockingSanity:backend:tests
# Runtime: python
# Purpose: Confirm refuses to lock a train-bearing plan on unsound interlocking; fails closed + atomic (#1249).
"""Confirm-gate validators for ``planner.plan.confirm-requires-interlocking-sanity``.

Proves the Confirm gate (``PlanSession.confirm``) refuses to lock a plan whose
kept train units reference an unsound interlocking, fails **closed** when the
validators crash, and is **atomic** — every failure path leaves
``PlanSession.locked is False``. A kept train with no interlocking reference is a
direct train and locks normally.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import pytest
import yaml

from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.interlocking import (
    load_interlocking,
    project_route_to_train_sequence,
    route_projection_digest,
)
from atdd.planner.interlocking.tests._fixtures import interlocking_doc, write_tree
from atdd.planner.commands.plan_session import PlanSession, SessionGateError, Step, Unit, Verdict

pytestmark = [pytest.mark.platform]

_INTERLOCKING_ID = "interlocking:match-resolution"


# ---------------------------------------------------------------------------
# fixtures: a fully-valid interlocking + train tree (#1248 write_tree, with the
# placeholder projection digests + payload contract body filled in so EVERY
# #1249 sanity rule is satisfied).
# ---------------------------------------------------------------------------
def _write_valid_tree(root: Path) -> Path:
    doc = interlocking_doc()
    il_path = write_tree(root, doc)
    # the message payload references contract `match:result`; give it a body whose
    # $id IS that identity so planner.train.interlocking-payload-contract-body-required
    # resolves it (by identity, not filename — #1314 item C).
    cdir = root / "plan" / "contracts"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "result.schema.json").write_text('{"$id": "match:result"}')
    # fill the placeholder projection digests with the computed values.
    il = load_interlocking(il_path)
    for r in doc["routes"]:
        steps = project_route_to_train_sequence(il, r["route_id"])
        fields = tuple(r["projection"].get("fields",
                                           ["step", "intent", "from", "to", "artifact"]))
        r["projection"]["expected_sequence_digest"] = route_projection_digest(steps, fields)
    il_path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return il_path


def _session_with_kept_train(root: Path, *, interlocking: bool) -> PlanSession:
    s = PlanSession(session_id="s1")
    s.step = Step.CONFIRM.value
    s.issue_ref = "demo-slug"
    spec = {"source_interlocking": {"interlocking_id": _INTERLOCKING_ID,
                                    "route_id": "nominal-all-voted"}} if interlocking else {}
    s.add_unit(Unit(kind="train", ref="3007-match-resolution-standard",
                    verdict=Verdict.KEEP.value, spec=spec))
    return s


# ---------------------------------------------------------------------------
# the bound validator + behaviour tests
# ---------------------------------------------------------------------------
def test_confirm_requires_interlocking_sanity(tmp_path: Path) -> None:
    """A kept train whose interlocking is UNSOUND blocks Confirm; a sound one locks."""
    rule = bind_rule("planner.plan.confirm-requires-interlocking-sanity")
    assert rule.rule_id == "planner.plan.confirm-requires-interlocking-sanity"

    il_path = _write_valid_tree(tmp_path)
    # sound -> locks
    s = _session_with_kept_train(tmp_path, interlocking=True)
    s.confirm(root=tmp_path)
    assert s.locked is True

    # break it: untype the message payload -> sanity fails -> Confirm refuses.
    doc = yaml.safe_load(il_path.read_text())
    doc["messages"][0]["payload"] = {"contract": None, "no_payload_reason": None}
    il_path.write_text(yaml.safe_dump(doc, sort_keys=False))
    s2 = _session_with_kept_train(tmp_path, interlocking=True)
    with pytest.raises(SessionGateError):
        s2.confirm(root=tmp_path)
    assert s2.locked is False


def test_confirm_failure_leaves_session_unlocked(tmp_path: Path) -> None:
    """Atomicity: a missing interlocking raises and never sets locked."""
    _write_valid_tree(tmp_path)
    (tmp_path / "plan" / "_trains" / "_interlockings" / "match-resolution.yaml").unlink()
    s = _session_with_kept_train(tmp_path, interlocking=True)
    with pytest.raises(SessionGateError):
        s.confirm(root=tmp_path)
    assert s.locked is False


def test_confirm_fails_closed_on_interlocking_validator_crash(tmp_path: Path, monkeypatch) -> None:
    """If the sanity validators crash, Confirm fails closed (raises, stays unlocked)."""
    _write_valid_tree(tmp_path)

    def _boom(*_a, **_k):
        raise RuntimeError("synthetic validator crash")

    monkeypatch.setattr(
        "atdd.planner.interlocking.sanity.interlocking_violations", _boom)
    s = _session_with_kept_train(tmp_path, interlocking=True)
    with pytest.raises(SessionGateError):
        s.confirm(root=tmp_path)
    assert s.locked is False


def test_confirm_allows_direct_train_when_no_interlocking_policy_requires_one(tmp_path: Path) -> None:
    """A kept train with NO interlocking reference is a direct train -> locks."""
    s = _session_with_kept_train(tmp_path, interlocking=False)
    s.confirm(root=tmp_path)
    assert s.locked is True


def test_confirm_unchanged_when_no_kept_train_units(tmp_path: Path) -> None:
    """No kept train units -> the gate is a no-op (existing behaviour preserved)."""
    s = PlanSession(session_id="s2")
    s.step = Step.CONFIRM.value
    s.issue_ref = "demo-slug"
    s.add_unit(Unit(kind="feature", ref="feat-x", verdict=Verdict.KEEP.value, spec={}))
    s.confirm(root=tmp_path)
    assert s.locked is True
