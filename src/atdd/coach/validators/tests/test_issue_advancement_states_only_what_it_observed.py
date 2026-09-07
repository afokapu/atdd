"""issue_advancement states what it observed, and its remedy is legal (issue #1748).

Observed on PR ``#1743`` / issue ``#1721``, 2026-08-04, in ``validate-coach``::

    [disposition gate] issue_advancement: 0 unsuppressed violation(s)

      validator=issue_advancement: 1 legacy (no rule_id) violation(s) — strict by default:
        PR #1743 merged (unknown) but linked issue #1721 is still at PLANNED — expected
        phase advancement after merge. Fix: atdd coach transition 1721 <next-phase>
        (e.g. "REFACTOR" or "COMPLETE"; see CLAUDE.md::state_machine.transitions for the
        valid transitions out of PLANNED).

Measured at the same moment: ``PR #1743  state=open  merged=false  merged_at=null``.

Three defects in one message, pinned here in the same order:

1. **A fact was invented.** The PR was OPEN. ``merged (unknown)`` is a missing
   ``mergedAt`` rendered into a sentence whose grammar already assumed the merge.
2. **The remedy prescribed a lifecycle bypass.** Followed verbatim from PLANNED,
   ``transition 1721 REFACTOR|COMPLETE`` skips RED, GREEN and SMOKE — it reaches
   a phase meaning "implemented and verified" with no failing test ever written
   and no smoke run ever executed.
3. **The header contradicted itself.** ``0 unsuppressed`` above ``1 legacy``.

And the condition the check exists for — a genuinely merged PR whose issue did
not advance — must survive all three fixes. It is real, and it is pinned last.
"""
from __future__ import annotations

import pytest

from _pytest.outcomes import Failed

from atdd.coach.gate.phase_edges import PhaseMachineUnavailable
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.validators import test_issue_advancement as mod
from atdd.coach.validators._observation import COULD_NOT_CHECK_PREFIX


def _issue(phase="PLANNED", state="OPEN", labels=None):
    lbls = list(labels or [])
    if phase is not None:
        lbls.append({"name": f"atdd:{phase}"})
    return {"state": state, "labels": lbls}


class FakePRManager:
    """PRManager stand-in: pr_number -> the dict resolve_linked_issue returns."""

    def __init__(self, resolutions=None):
        self._resolutions = resolutions or {}

    def resolve_linked_issue(self, pr_number):
        return self._resolutions.get(pr_number)


def _mgr(pr_number=1743, issue_number=1721, phase="PLANNED", pr_data=None):
    """The #1743/#1721 shape, with the PR's own row under the caller's control."""
    return FakePRManager({
        pr_number: {
            "issue_number": issue_number,
            "phase_label": phase,
            "strategy": "api",
            "pr_data": pr_data if pr_data is not None else {},
            "issue_data": _issue(phase=phase),
        }
    })


OPEN_PR = {"state": "OPEN", "mergedAt": None}
MERGED_PR = {"state": "MERGED", "mergedAt": "2026-08-04T18:03:00Z"}


# ---------------------------------------------------------------------------
# 1. An open PR is never described as merged
# ---------------------------------------------------------------------------


class TestStatesOnlyWhatItObserved:
    def test_an_open_pr_produces_no_message_at_all(self):
        """state=open merged=false merged_at=null — nothing is owed before a merge."""
        message = mod._evaluate_pr(_mgr(pr_data=OPEN_PR), {"number": 1743})
        assert message is None

    def test_an_open_pr_is_never_called_merged(self):
        """The exact false claim from #1743, in whichever path reaches it."""
        for pr in ({"number": 1743}, {"number": 1743, "state": "OPEN"}):
            message = mod._evaluate_pr(_mgr(pr_data=OPEN_PR), pr)
            assert message is None or "merged" not in message.split("Fix:")[0]

    def test_merged_unknown_is_never_emitted(self):
        """`merged (unknown)` was a missing timestamp wearing a merge's grammar."""
        merged_no_timestamp = {"state": "MERGED", "mergedAt": None}
        message = mod._evaluate_pr(_mgr(pr_data=merged_no_timestamp), {"number": 1743})
        assert message is not None
        assert "(unknown)" not in message
        assert "PR #1743 merged but" in message

    def test_an_indeterminate_merge_state_is_could_not_check(self):
        """Three states, three answers — not one sentence that only knows merged."""
        message = mod._evaluate_pr(_mgr(pr_data={}), {"number": 1743})
        assert message is not None
        assert message.startswith(COULD_NOT_CHECK_PREFIX)
        assert "merge state could not be read" in message

    def test_the_pr_row_wins_over_the_fetched_row(self):
        """The advisory sweep passes real merged rows; they must be believed."""
        message = mod._evaluate_pr(
            _mgr(pr_data={}), {"number": 1743, **MERGED_PR},
        )
        assert message is not None
        assert not message.startswith(COULD_NOT_CHECK_PREFIX)
        assert "2026-08-04T18:03:00Z" in message


# ---------------------------------------------------------------------------
# 2. The remedy comes from the phase machine and cannot skip a phase
# ---------------------------------------------------------------------------


class TestRemedyIsDerivedFromThePhaseMachine:
    @pytest.mark.parametrize(
        "phase,expected", [("INIT", "PLANNED"), ("PLANNED", "RED")],
    )
    def test_it_names_the_next_legal_phase(self, phase, expected):
        remedy = mod.next_phase_remedy(phase, 1721)
        assert f"atdd coach transition 1721 {expected}" in remedy

    @pytest.mark.parametrize("phase", ["INIT", "PLANNED"])
    def test_it_never_prescribes_refactor_or_complete(self, phase):
        """The serious half: following this verbatim must not skip RED/GREEN/SMOKE."""
        remedy = mod.next_phase_remedy(phase, 1721)
        assert "REFACTOR" not in remedy
        assert "COMPLETE" not in remedy

    def test_it_never_prescribes_an_escape(self):
        """BLOCKED/OBSOLETE are declared transitions but they are not advancement."""
        remedy = mod.next_phase_remedy("PLANNED", 1721)
        assert "BLOCKED" not in remedy
        assert "OBSOLETE" not in remedy

    def test_the_live_message_carries_the_derived_remedy(self):
        message = mod._evaluate_pr(_mgr(phase="PLANNED", pr_data=MERGED_PR),
                                   {"number": 1743})
        assert "atdd coach transition 1721 RED" in message

    def test_an_unreadable_machine_names_no_phase_at_all(self, monkeypatch):
        """Inventing a remedy when the lifecycle is unreadable is the same defect."""
        def _boom(*_a, **_k):
            raise PhaseMachineUnavailable("the phase machine could not be read")

        monkeypatch.setattr(mod, "phase_machine", _boom)
        remedy = mod.next_phase_remedy("PLANNED", 1721)
        assert "atdd coach transition 1721 " not in remedy
        assert "phase_machine.convention.yaml" in remedy

    def test_the_remedy_points_at_the_machine_not_at_claude_md(self):
        """CLAUDE.md's duplicate state_machine table was removed in #888."""
        remedy = mod.next_phase_remedy("PLANNED", 1721)
        assert "CLAUDE.md" not in remedy
        assert "phase_machine.convention.yaml" in remedy


# ---------------------------------------------------------------------------
# 3. The header says how many violations there were
# ---------------------------------------------------------------------------


class TestHeaderCountMatchesViolationCount:
    def test_one_legacy_violation_is_reported_as_one(self):
        with pytest.raises(Failed) as excinfo:
            assert_disposition_satisfied(
                validator_id="issue_advancement",
                violations=["PR #1743 merged but linked issue #1721 ..."],
            )
        report = str(excinfo.value)
        assert "issue_advancement: 1 unsuppressed violation(s)" in report
        assert "0 unsuppressed violation(s)" not in report

    def test_the_count_tracks_the_list(self):
        with pytest.raises(Failed) as excinfo:
            assert_disposition_satisfied(
                validator_id="issue_advancement",
                violations=["first violation", "second violation"],
            )
        assert "issue_advancement: 2 unsuppressed violation(s)" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 4. The real condition is preserved
# ---------------------------------------------------------------------------


class TestTheRealConditionStillFails:
    @pytest.mark.parametrize("phase", ["INIT", "PLANNED"])
    def test_a_merged_pr_whose_issue_did_not_advance_still_fails(self, phase):
        message = mod._evaluate_pr(_mgr(phase=phase, pr_data=MERGED_PR),
                                   {"number": 1743})
        assert message is not None
        assert not message.startswith(COULD_NOT_CHECK_PREFIX)
        assert f"still at {phase}" in message

    def test_a_merged_pr_whose_issue_did_advance_passes(self):
        assert mod._evaluate_pr(_mgr(phase="RED", pr_data=MERGED_PR),
                                {"number": 1743}) is None

    def test_the_existing_skips_are_untouched_by_the_merge_check(self):
        """Closed / terminal / non-lifecycle short-circuit before merge state."""
        closed = FakePRManager({1743: {
            "issue_number": 1721, "phase_label": "PLANNED", "strategy": "api",
            "pr_data": MERGED_PR, "issue_data": _issue(state="CLOSED"),
        }})
        assert mod._evaluate_pr(closed, {"number": 1743, **MERGED_PR}) is None

        tracking = FakePRManager({1743: {
            "issue_number": 1721, "phase_label": "INIT", "strategy": "api",
            "pr_data": MERGED_PR,
            "issue_data": _issue(phase="INIT", labels=[{"name": "tracking"}]),
        }})
        assert mod._evaluate_pr(tracking, {"number": 1743, **MERGED_PR}) is None


# ---------------------------------------------------------------------------
# _merge_state, directly
# ---------------------------------------------------------------------------


class TestMergeState:
    def test_merged_at_settles_it(self):
        assert mod._merge_state({"mergedAt": "2026-08-04T18:03:00Z"}) is True

    def test_state_merged_settles_it_without_a_timestamp(self):
        assert mod._merge_state({"state": "MERGED", "mergedAt": None}) is True

    @pytest.mark.parametrize("state", ["OPEN", "CLOSED", "DRAFT", "open"])
    def test_an_unmerged_state_settles_it(self, state):
        assert mod._merge_state({"state": state, "mergedAt": None}) is False

    def test_nothing_to_read_is_none_not_a_guess(self):
        assert mod._merge_state({}, None, {"number": 1743}) is None

    def test_the_first_source_that_answers_wins(self):
        assert mod._merge_state({"number": 1743}, {"state": "OPEN"}) is False
