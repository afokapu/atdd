# URN: test:author-plan-substrate:author-plan-spine:C008-UNIT-004-plan-unit-upserts-by-ref
# Acceptance: acc:author-plan-substrate:C008-UNIT-004-plan-unit-upserts-by-ref
# WMBT: wmbt:author-plan-substrate:C008
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C008-UNIT-004 (plan spine) — `atdd plan unit` upserts by `ref`.

``ref`` identifies a unit within a session: ``PlanSession._unit()`` has always
resolved by ``ref`` alone. Appending a second unit under an existing ref
therefore made the session ambiguous — ``decide()`` reached only the first while
``author()`` wrote both. Re-stating a unit is the normal Prepare loop (draft,
look, re-draft), so it updates in place.

Changing a decided unit's spec resets its verdict: ``confirm()`` requires a
terminal verdict, and the thing the operator decided on is no longer the thing
in the session. An identical replay is a no-op, so it never discards a verdict
or the modification a pivot recorded.

RED: ``add_unit`` appended unconditionally — adding ref ``w1`` twice gave
``units: 2 | refs: ['w1', 'w1']``.

Refs #1235.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Unit, Verdict,
)
from atdd.planner.commands.plan_session_cli import run

_FIRST = {"wagon": "play-audio", "description": "play audio on the commute"}
_SECOND = {"wagon": "play-audio", "description": "play audio while driving"}


def _to_prepare(root: Path, sid: str) -> None:
    assert run(["--root", str(root), "start", "--id", sid, "--main-job", "job", "--issue", "iss"]) == 0
    assert run(["--root", str(root), "advance", "--id", sid, "--step", "attach"]) == 0
    assert run(["--root", str(root), "source", "--id", sid, "a source"]) == 0
    assert run(["--root", str(root), "advance", "--id", sid, "--step", "compose"]) == 0


def _unit(root: Path, sid: str, spec: dict, *, kind: str = "wagon", ref: str = "w1") -> int:
    return run(["--root", str(root), "unit", "--id", sid, "--kind", kind,
                "--ref", ref, "--spec", json.dumps(spec)])


def _units(root: Path, sid: str) -> list:
    state = json.loads((root / ".atdd" / "runtime" / "plan-sessions" / sid / "session.json").read_text())
    return state["units"]


def test_restating_a_ref_updates_in_place_rather_than_duplicating(tmp_path):
    _to_prepare(tmp_path, "s1")
    assert _unit(tmp_path, "s1", _FIRST) == 0
    assert _unit(tmp_path, "s1", _SECOND) == 0

    units = _units(tmp_path, "s1")
    assert [u["ref"] for u in units] == ["w1"], "a re-stated ref must not append a duplicate"
    assert units[0]["spec"] == _SECOND, "the later spec wins"


def test_distinct_refs_still_accumulate(tmp_path):
    _to_prepare(tmp_path, "s2")
    assert _unit(tmp_path, "s2", _FIRST, ref="w1") == 0
    assert _unit(tmp_path, "s2", _FIRST, ref="w2") == 0
    assert [u["ref"] for u in _units(tmp_path, "s2")] == ["w1", "w2"]


def test_changing_a_decided_units_spec_resets_its_verdict(tmp_path):
    """The operator decided on the old spec; the new one must be re-decided."""
    _to_prepare(tmp_path, "s3")
    assert _unit(tmp_path, "s3", _FIRST) == 0
    assert run(["--root", str(tmp_path), "decide", "--id", "s3", "--ref", "w1", "--verdict", "keep"]) == 0
    assert _units(tmp_path, "s3")[0]["verdict"] == Verdict.KEEP.value

    assert _unit(tmp_path, "s3", _SECOND) == 0
    assert _units(tmp_path, "s3")[0]["verdict"] == Verdict.PENDING.value, (
        "a changed spec is no longer the thing the operator kept")


def test_restating_an_identical_spec_preserves_the_verdict(tmp_path):
    """A replay is a no-op — it must not silently discard a decision."""
    _to_prepare(tmp_path, "s4")
    assert _unit(tmp_path, "s4", _FIRST) == 0
    assert run(["--root", str(tmp_path), "decide", "--id", "s4", "--ref", "w1", "--verdict", "keep"]) == 0

    assert _unit(tmp_path, "s4", _FIRST) == 0
    assert _units(tmp_path, "s4")[0]["verdict"] == Verdict.KEEP.value


def test_a_replay_preserves_the_modification_a_pivot_recorded(tmp_path):
    _to_prepare(tmp_path, "s5")
    assert _unit(tmp_path, "s5", _FIRST) == 0
    assert run(["--root", str(tmp_path), "decide", "--id", "s5", "--ref", "w1",
                "--verdict", "pivot", "--mod", "narrow the scope"]) == 0

    assert _unit(tmp_path, "s5", _FIRST) == 0
    assert _units(tmp_path, "s5")[0]["modification"] == "narrow the scope"


def test_reusing_a_ref_under_a_different_kind_is_refused(tmp_path, capsys):
    """Not an update — silently changing kind would pick a different author writer."""
    _to_prepare(tmp_path, "s6")
    assert _unit(tmp_path, "s6", _FIRST, kind="wagon") == 0
    assert _unit(tmp_path, "s6", {"feature": "x"}, kind="feature") == 2

    err = capsys.readouterr().err
    assert "w1" in err and "wagon" in err and "feature" in err
    assert "Traceback" not in err
    units = _units(tmp_path, "s6")
    assert len(units) == 1 and units[0]["kind"] == "wagon", "the refusal must not mutate the session"


def test_add_unit_refuses_a_kind_conflict_at_the_api(tmp_path):
    s = PlanSession("api", main_job="job", issue_ref="iss")
    s.add_unit(Unit(kind="wagon", ref="w1", spec={"a": 1}))
    with pytest.raises(SessionGateError, match="already exists as kind"):
        s.add_unit(Unit(kind="feature", ref="w1", spec={"a": 1}))


def test_an_upserted_unit_stays_reachable_by_decide(tmp_path):
    """The point of the fix: one ref resolves to exactly one unit."""
    _to_prepare(tmp_path, "s7")
    assert _unit(tmp_path, "s7", _FIRST) == 0
    assert _unit(tmp_path, "s7", _SECOND) == 0
    assert run(["--root", str(tmp_path), "decide", "--id", "s7", "--ref", "w1", "--verdict", "keep"]) == 0

    units = _units(tmp_path, "s7")
    assert [u["verdict"] for u in units] == [Verdict.KEEP.value], (
        "with a duplicate present, decide() reached only the first unit while "
        "author() would have written both")
