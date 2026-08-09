"""An unreadable PR→issue link refuses instead of passing (issue #1747).

``coach.pr.merge-blocks-on-pre-smoke-close`` is strict and guards the 2026-05-13
substrate-asymmetry incident (``#681``). It returned PASS and then FAIL on the
IDENTICAL head sha ``54bdad8af``:

    12:58:31Z  event=push          SUCCESS     <- PR #1757 did not exist yet
    13:08:44Z  PR #1757 created
    13:08:46Z  event=pull_request  FAILURE     <- two seconds later

Nothing the validator examines changed. The pass was vacuous: no PR→issue link
was resolvable, and the check returned PASS rather than "I could not resolve the
link". These tests pin the four things the fix has to be simultaneously — a
refusal on an unreadable link, and no weakening anywhere else:

1. A declared auto-close whose link cannot be read  -> COULD_NOT_CHECK (blocks).
2. A PR that declares no auto-close                 -> NOT_APPLICABLE (merges).
3. A pre-SMOKE issue behind a readable link         -> still FAILs.
4. A REFACTOR/COMPLETE issue behind one             -> still PASSes.

Driven from synthetic fixtures — no network. The fake borrows ``PRManager``'s own
``_CLOSING_RE`` and its two auto-closing strategies rather than re-deriving what
"declares an auto-close" means, so this test cannot drift away from the resolver
it is standing in for.
"""
from __future__ import annotations

import pytest

from atdd.coach.commands.pr import PRManager
from atdd.coach.gate.decision import GateVerdict
from atdd.coach.validators import test_pr_merge_blocks_pre_smoke_close as mod
from atdd.coach.validators._observation import (
    COULD_NOT_CHECK_PREFIX,
    Observation,
    Reading,
)

RULE_ID = "coach.pr.merge-blocks-on-pre-smoke-close"


class FakePRManager:
    """PRManager stand-in whose link-declaration logic is the real one."""

    # The two strategies that actually fire GitHub's auto-close, taken verbatim
    # from PRManager so "declares an auto-close" means the same thing here.
    _CLOSING_RE = PRManager._CLOSING_RE
    _resolve_via_api = PRManager._resolve_via_api
    _resolve_via_body = PRManager._resolve_via_body

    def __init__(self, resolutions=None):
        self._resolutions = resolutions or {}

    def resolve_linked_issue(self, pr_number):
        return self._resolutions.get(pr_number)


def _pr(number=1757, body="", closing=None):
    return {
        "number": number,
        "title": f"a change (#{number})",
        "body": body,
        "headRefName": "feat/x",
        "state": "OPEN",
        "closingIssuesReferences": list(closing or []),
    }


def _issue(*, atdd_issue=True, phase=None, state="OPEN"):
    labels = []
    if atdd_issue:
        labels.append({"name": "atdd-issue"})
    if phase:
        labels.append({"name": f"atdd:{phase}"})
    return {"state": state, "labels": labels}


def _resolution(issue_number=1756, phase="INIT", strategy="api", issue=None):
    return {
        "issue_number": issue_number,
        "phase_label": phase,
        "strategy": strategy,
        "pr_data": {},
        "issue_data": issue if issue is not None else _issue(phase=phase),
    }


# ---------------------------------------------------------------------------
# The vocabulary itself
# ---------------------------------------------------------------------------


class TestObservationVocabulary:
    def test_unreadable_maps_to_could_not_check_and_blocks(self):
        reading = Reading.unreadable("the link could not be read", subject=1757)
        assert reading.verdict is GateVerdict.COULD_NOT_CHECK
        assert reading.blocks is True

    def test_no_obligation_maps_to_not_applicable_and_proceeds(self):
        reading = Reading.no_obligation("no auto-close declared", subject=1757)
        assert reading.verdict is GateVerdict.NOT_APPLICABLE
        assert reading.blocks is False

    def test_observed_leaves_the_verdict_to_the_rule(self):
        """OBSERVED must NOT answer PASS — that substitution is the whole defect."""
        reading = Reading.observed({"issue_number": 1}, subject=1757)
        assert reading.verdict is None
        assert reading.blocks is False
        assert Observation.OBSERVED.to_verdict() is None


# ---------------------------------------------------------------------------
# 1. An unreadable declared link refuses
# ---------------------------------------------------------------------------


class TestUnreadableLinkRefuses:
    def test_api_declared_close_that_does_not_resolve_is_could_not_check(self):
        """closingIssuesReferences says it WILL close #1756; resolution says nothing."""
        pr = _pr(1757, closing=[{"number": 1756}])
        reading = mod.read_pr_issue_link(FakePRManager(), pr)
        assert reading.observation is Observation.UNREADABLE
        assert reading.verdict is GateVerdict.COULD_NOT_CHECK
        assert "#1756" in reading.reason

    def test_body_declared_close_that_does_not_resolve_is_could_not_check(self):
        pr = _pr(1757, body="Closes #1756\n\nsome description")
        reading = mod.read_pr_issue_link(FakePRManager(), pr)
        assert reading.observation is Observation.UNREADABLE

    def test_it_becomes_a_blocking_violation_not_a_silent_skip(self):
        pr = _pr(1757, closing=[{"number": 1756}])
        readings = [mod.read_pr_issue_link(FakePRManager(), pr)]

        violations = mod.evaluate_link_readings(readings)

        assert len(violations) == 1, "an unresolvable link must not pass silently"
        assert violations[0].rule_id == RULE_ID
        assert violations[0].detail.startswith(COULD_NOT_CHECK_PREFIX)

    def test_the_refusal_is_attributable_to_its_own_pr(self):
        """Location must carry PR#<n>: or _pr_scope cannot scope it (E070/#1478)."""
        pr = _pr(1757, closing=[{"number": 1756}])
        violations = mod.evaluate_link_readings(
            [mod.read_pr_issue_link(FakePRManager(), pr)]
        )
        assert violations[0].location == "PR#1757:0"
        # An innocent branch is still not failed by a stranger's unreadable link.
        assert mod.select_blocking_violations(violations, current_pr=999) == []
        assert mod.select_blocking_violations(violations, current_pr=1757) == violations

    def test_the_refusal_says_what_would_make_it_observable(self):
        pr = _pr(1757, closing=[{"number": 1756}])
        reason = mod.read_pr_issue_link(FakePRManager(), pr).reason
        assert "gh pr view 1757" in reason
        assert "gh issue view 1756" in reason

    def test_a_weak_fallback_cannot_stand_in_for_the_declared_target(self):
        """`Closes #1756` unread, branch-slug matched #1600 instead → not observed.

        Branch-slug and title matching identify an issue but do NOT fire GitHub's
        auto-close. Letting one satisfy a reference whose own read failed is the
        same substitution in a subtler place.
        """
        pr = _pr(1757, closing=[{"number": 1756}])
        mgr = FakePRManager({1757: _resolution(1600, phase="REFACTOR",
                                               strategy="manifest")})
        reading = mod.read_pr_issue_link(mgr, pr)
        assert reading.observation is Observation.UNREADABLE
        assert "#1756" in reading.reason and "#1600" in reading.reason

    def test_atdd_issue_with_no_phase_label_is_could_not_check(self):
        """The link read fine; the phase this gate compares against did not."""
        pr = _pr(1757, closing=[{"number": 1756}])
        mgr = FakePRManager({1757: _resolution(
            1756, phase=None, issue=_issue(atdd_issue=True, phase=None),
        )})
        reading = mod.read_pr_issue_link(mgr, pr)
        assert reading.observation is Observation.UNREADABLE
        assert "atdd:<PHASE>" in reading.reason


# ---------------------------------------------------------------------------
# 2. "No PR" / "no auto-close" is NOT_APPLICABLE — ordinary PRs still merge
# ---------------------------------------------------------------------------


class TestNotApplicableStaysMergeable:
    def test_pr_declaring_no_auto_close_is_no_obligation(self):
        """`Refs #1756` does not fire auto-close, so this gate is owed nothing."""
        pr = _pr(1757, body="Refs #1756 — a partial step")
        reading = mod.read_pr_issue_link(FakePRManager(), pr)
        assert reading.observation is Observation.NO_OBLIGATION
        assert reading.verdict is GateVerdict.NOT_APPLICABLE

    def test_no_obligation_contributes_no_violation(self):
        pr = _pr(1757, body="Refs #1756")
        readings = [mod.read_pr_issue_link(FakePRManager(), pr)]
        assert mod.evaluate_link_readings(readings) == []

    def test_a_non_atdd_issue_without_a_phase_label_is_no_obligation(self):
        """Closing an ordinary bug report must not refuse — that would strand the repo."""
        pr = _pr(1757, closing=[{"number": 400}])
        mgr = FakePRManager({1757: _resolution(
            400, phase=None, issue=_issue(atdd_issue=False, phase=None),
        )})
        reading = mod.read_pr_issue_link(mgr, pr)
        assert reading.observation is Observation.NO_OBLIGATION
        assert mod.evaluate_link_readings([reading]) == []

    def test_an_empty_repo_scan_is_still_green(self):
        assert mod.evaluate_link_readings([]) == []


# ---------------------------------------------------------------------------
# 3 + 4. The live rule is untouched in both directions
# ---------------------------------------------------------------------------


class TestTheRuleItselfIsNotWeakened:
    @pytest.mark.parametrize("phase", ["INIT", "PLANNED", "RED", "GREEN"])
    def test_a_readable_pre_smoke_link_still_fails(self, phase):
        """#1743, #1744, #1752, #1757, #1660 — every one of those was the gate working."""
        pr = _pr(1757, closing=[{"number": 1756}])
        mgr = FakePRManager({1757: _resolution(1756, phase=phase, strategy="api")})

        violations = mod.evaluate_link_readings([mod.read_pr_issue_link(mgr, pr)])

        assert len(violations) == 1
        assert f"atdd:{phase}" in violations[0].detail
        assert not violations[0].detail.startswith(COULD_NOT_CHECK_PREFIX), (
            "a pre-SMOKE offender is a FAIL, not a could-not-check"
        )

    @pytest.mark.parametrize("phase", ["SMOKE", "REFACTOR", "COMPLETE"])
    def test_a_readable_merge_eligible_link_still_passes(self, phase):
        """#1721/#1735/#1653/#1671 cleared this on rerun and merged. Stays green."""
        pr = _pr(1757, closing=[{"number": 1756}])
        mgr = FakePRManager({1757: _resolution(1756, phase=phase, strategy="api")})

        assert mod.evaluate_link_readings([mod.read_pr_issue_link(mgr, pr)]) == []

    def test_a_weak_manifest_link_at_green_still_passes(self):
        """Manifest/title linkage does not fire auto-close, so it is not blocked."""
        pr = _pr(1757, body="no keyword here")
        mgr = FakePRManager({1757: _resolution(1756, phase="GREEN", strategy="manifest")})
        assert mod.evaluate_link_readings([mod.read_pr_issue_link(mgr, pr)]) == []


# ---------------------------------------------------------------------------
# The flip, reproduced: one commit, two runs, opposite readings
# ---------------------------------------------------------------------------


def test_the_1757_flip_cannot_read_as_green_on_either_run():
    """Head sha 54bdad8af, judged twice ten minutes apart.

    12:58:31Z the PR did not exist, so nothing about it was observed; 13:08:46Z it
    did, and the link resolved to #1756 at INIT. Under the old code the first run
    reported PASS — a verdict it had no observation to support. Neither run may
    now produce a green that claims to have checked PR #1757.
    """
    # 13:08:46Z — the link resolves, the issue is at INIT: a real FAIL.
    pr = _pr(1757, closing=[{"number": 1756}])
    mgr = FakePRManager({1757: _resolution(1756, phase="INIT", strategy="api")})
    after = mod.evaluate_link_readings([mod.read_pr_issue_link(mgr, pr)])
    assert len(after) == 1

    # 12:58:31Z — same PR row, but nothing resolves behind it. NOT a pass.
    before = mod.evaluate_link_readings(
        [mod.read_pr_issue_link(FakePRManager(), pr)]
    )
    assert len(before) == 1
    assert before[0].detail.startswith(COULD_NOT_CHECK_PREFIX)
