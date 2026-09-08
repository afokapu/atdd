# URN: test:atdd-plan-core:session-machine:confirm-lock-enforces
# Issue: #1505
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1505 — the Confirm lock must ENFORCE, not merely mark.

``confirm()`` is the conversational->deterministic boundary and the host for three
fail-closed validations: interlocking sanity (#1249), verb-object naming (#1276),
and artifact/contract naming (#1329). Before this issue, ``locked`` was written by
``confirm()`` and read only by ``author()`` — nothing in between consulted it. That
left an exploit:

    confirm()            -> locked = True
    add_unit(smuggled)   -> accepted, nothing checks the flag
    advance(PREPARE)     -> backtracks `step`, leaves `locked = True` stale
    advance(CONFIRM)
    advance(AUTHORED)    -> _gate_ok reads the STALE flag and lets it through

so a unit authored this way was never seen by any of the three validators. The gate
read as protective and was not, which is worse than an absent gate because it is
trusted.

These tests pin the fix from both sides: the lock refuses mutation, backtracking
clears it, and ``reopen()`` is a real, reachable escape. A guard whose documented
escape cannot be reached is the ``[mass-delete-approved]`` defect repeated, so the
escape is pinned as hard as the refusal.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit, Verdict,
)


def _confirmed_session(root) -> PlanSession:
    """A session walked to Confirm and locked, with one kept unit.

    Kind ``wmbt`` deliberately: it carries no train interlocking and no wagon
    produce[], so ``confirm()`` exercises the lock without dragging the #1249/#1276/
    #1329 validator bodies into a test about the lock itself.
    """
    s = PlanSession("s-1505", issue_ref="enforce-plan-confirm-lock")
    s.main_job = "enforce the confirm lock"
    s.advance(Step.ATTACH)
    s.sources.append({"type": "text", "value": "src/atdd/planner/commands/plan_session.py"})
    s.advance(Step.COMPOSE)
    s.add_unit(Unit(kind="wmbt", ref="wmbt-one", verdict=Verdict.KEEP.value))
    s.advance(Step.RATIFY)
    s.confirm(root)
    assert s.locked is True  # precondition
    return s


# ---- side one: the lock refuses mutation --------------------------------------

def test_add_unit_is_refused_while_locked(tmp_path):
    """What you confirmed is what gets authored (operator decision, #1235)."""
    s = _confirmed_session(tmp_path)
    with pytest.raises(SessionGateError) as exc:
        s.add_unit(Unit(kind="wmbt", ref="smuggled-unit"))
    assert "reopen" in str(exc.value)  # the refusal must name the escape
    assert [u["ref"] for u in s.units] == ["wmbt-one"]  # and must not have mutated


class _RecordingElicit:
    """A real elicit stub, so the test can only fail on the missing lock.

    Passing ``None`` here would make the test red with an incidental AttributeError
    from inside ``decide()`` rather than on the refusal being absent — red for the
    wrong reason reads the same in a summary as red for the right one.
    """

    def __init__(self):
        self.calls = 0

    def elicit(self, req):  # pragma: no cover - must never be reached while locked
        self.calls += 1
        raise AssertionError("decide() consulted the operator on a LOCKED session")


def test_upserting_an_existing_unit_is_refused_while_locked(tmp_path):
    """The #1507 upsert path is a mutation too, and must be behind the same lock.

    ``add_unit`` no longer only appends: re-stating an existing ``ref`` with a
    changed spec REWRITES that unit and resets its verdict to PENDING. On a locked
    session that rewrites a decomposition the operator already signed off, wearing
    the shape of an edit rather than an addition — the same bypass, different door.

    Without this test the guard could be moved below the ref scan and every other
    test here would still pass, leaving the upsert path unguarded.
    """
    s = _confirmed_session(tmp_path)
    with pytest.raises(SessionGateError) as exc:
        s.add_unit(Unit(kind="wmbt", ref="wmbt-one", spec={"changed": True}))
    assert "reopen" in str(exc.value)
    assert s.units[0]["spec"] == {}                       # not rewritten
    assert s.units[0]["verdict"] == Verdict.KEEP.value    # verdict not reset
    assert len(s.units) == 1


def test_decide_is_refused_while_locked(tmp_path):
    """Re-deciding a verdict post-Confirm is as much a mutation as adding a unit."""
    s = _confirmed_session(tmp_path)
    channel = _RecordingElicit()
    with pytest.raises(SessionGateError) as exc:
        s.decide("wmbt-one", channel)
    assert "reopen" in str(exc.value)
    assert channel.calls == 0  # refused BEFORE the elicit channel is opened
    assert s.units[0]["verdict"] == Verdict.KEEP.value


def test_backtracking_clears_the_lock(tmp_path):
    """`advance()` to an earlier step withdraws the operator's assertion.

    The flag asserts 'this exact unit set may be authored'. Once the operator steps
    back to edit, that assertion no longer describes anything true.
    """
    s = _confirmed_session(tmp_path)
    s.advance(Step.COMPOSE)
    assert s.locked is False


def test_the_1505_exploit_no_longer_reaches_authored(tmp_path):
    """THE ANCHOR — the exact sequence from the issue, which used to succeed.

    Mutate post-Confirm, backtrack, walk forward. Before the fix this ended at
    ``step == authored`` carrying a unit ``confirm()`` had never validated.
    """
    s = _confirmed_session(tmp_path)

    # leg 1: the mutation is refused outright
    with pytest.raises(SessionGateError):
        s.add_unit(Unit(kind="wmbt", ref="smuggled-unit"))

    # leg 2: even having backtracked first, AUTHORED requires a FRESH confirm()
    s.advance(Step.COMPOSE)
    s.add_unit(Unit(kind="wmbt", ref="smuggled-unit", verdict=Verdict.KEEP.value))
    s.advance(Step.RATIFY)
    with pytest.raises(SessionGateError) as exc:
        s.advance(Step.AUTHORED)
    assert "locked" in str(exc.value)
    assert s.step == Step.RATIFY.value
    assert s.locked is False


def test_author_is_refused_after_backtracking(tmp_path):
    """`author()` reads the same flag; backtracking must close that door too."""
    s = _confirmed_session(tmp_path)
    s.advance(Step.COMPOSE)
    s.advance(Step.RATIFY)
    with pytest.raises(SessionGateError) as exc:
        s.author(lambda kind, spec: None)
    assert "confirm-before-author" in str(exc.value)


# ---- side two: the escape is real and reachable -------------------------------

def test_reopen_clears_the_lock_and_returns_to_prepare(tmp_path):
    s = _confirmed_session(tmp_path)
    s.reopen()
    assert s.locked is False
    assert s.step == Step.COMPOSE.value


def test_reopen_preserves_verdicts(tmp_path):
    """Operator decision (#1505 decision 3): verdicts survive a reopen.

    Safe because ``confirm()`` re-runs all three validators against the CURRENT unit
    set regardless of verdict age — so preserving them bypasses nothing, while
    resetting them would punish large decompositions and discourage using the
    sanctioned escape at all.
    """
    s = _confirmed_session(tmp_path)
    s.reopen()
    assert s.units[0]["verdict"] == Verdict.KEEP.value


def test_reopen_is_refused_once_authored(tmp_path):
    """#1505 decision 2: artifacts are already on disk; reopening would orphan them."""
    s = _confirmed_session(tmp_path)
    s.advance(Step.AUTHORED)
    with pytest.raises(SessionGateError) as exc:
        s.reopen()
    assert "authored" in str(exc.value).lower()
    assert s.locked is True


def test_the_sanctioned_escape_works_end_to_end(tmp_path):
    """reopen -> amend -> confirm -> AUTHORED must SUCCEED.

    A guard whose documented escape is unreachable is a worse defect than the hole it
    closes. This is the test that keeps the refusal honest.
    """
    s = _confirmed_session(tmp_path)
    s.reopen()
    s.add_unit(Unit(kind="wmbt", ref="wmbt-two", verdict=Verdict.KEEP.value))
    s.advance(Step.RATIFY)
    s.confirm(tmp_path)                      # the fresh confirm the exploit skipped
    assert s.locked is True
    s.advance(Step.AUTHORED)
    assert s.step == Step.AUTHORED.value
    assert [u["ref"] for u in s.units] == ["wmbt-one", "wmbt-two"]
