# URN: test:judge-ambiguous-decisions:judge-and-issue-review:D002-UNIT-001-call-site-trigger-conditions-precise
# Acceptance: acc:judge-ambiguous-decisions:D002-UNIT-001-call-site-trigger-conditions-precise
# WMBT: wmbt:judge-ambiguous-decisions:D002
# Phase: RED
# Layer: unit
"""D002-UNIT-001 -- call site #1, #3, #4 trigger conditions are precise.

Per spec S6.9 (and issue #522):

  * Call site #1 (borderline tier-1) fires only when tier-1 has mixed
    pass/fail with ambiguous severity, OR a suppress-and-clean rule
    cluster touches recently-edited lines.
  * Call site #3 (retry-vs-escalate) fires only when retry_count equals
    max_retries minus one (the *next* attempt would consume the final
    retry).
  * Call site #4 (cross-phase regression) fires only when tier-1 in a
    later phase reveals violations that did not exist at the predecessor
    phase's exit commit.

When pre-conditions are not met, no judge call is made and no
judgments.jsonl line is appended.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Workspace fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


# ---------------------------------------------------------------------------
# Call site #1 -- borderline tier-1
# ---------------------------------------------------------------------------


class TestShouldFireBorderlineTier1:
    """``should_fire_borderline_tier1`` fires only on ambiguous tier-1
    results per spec S6.9 #1."""

    def test_mixed_pass_fail_with_ambiguous_severity_fires(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_borderline_tier1,
        )

        context = {
            "violations": [
                {"rule_id": "r1", "severity": 2, "disposition": "strict", "location": "a.py:10"},
                {"rule_id": "r2", "severity": 3, "disposition": "strict", "location": "b.py:20"},
            ],
            "total_rules": 3,
            "recently_edited_lines": [],
        }
        assert should_fire_borderline_tier1(context) is True

    def test_suppress_and_clean_cluster_near_recent_edits_fires(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_borderline_tier1,
        )

        context = {
            "violations": [
                {
                    "rule_id": "coder.logging.coach-silent-swallow",
                    "severity": 2,
                    "disposition": "suppress-and-clean",
                    "location": "src/foo.py:15",
                },
                {
                    "rule_id": "coder.logging.coach-silent-swallow",
                    "severity": 2,
                    "disposition": "suppress-and-clean",
                    "location": "src/foo.py:18",
                },
            ],
            "total_rules": 5,
            "recently_edited_lines": ["src/foo.py:14", "src/foo.py:17"],
        }
        assert should_fire_borderline_tier1(context) is True

    def test_clean_pass_does_not_fire(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_borderline_tier1,
        )

        context = {
            "violations": [],
            "total_rules": 5,
            "recently_edited_lines": [],
        }
        assert should_fire_borderline_tier1(context) is False

    def test_all_fail_high_severity_does_not_fire(self):
        """All violations at severity 4-5 with strict disposition are not
        ambiguous -- deterministic routing handles these."""
        from atdd.coach.commands.judge_call_sites import (
            should_fire_borderline_tier1,
        )

        context = {
            "violations": [
                {"rule_id": "r1", "severity": 4, "disposition": "strict", "location": "a.py:10"},
                {"rule_id": "r2", "severity": 5, "disposition": "strict", "location": "b.py:20"},
            ],
            "total_rules": 3,
            "recently_edited_lines": [],
        }
        assert should_fire_borderline_tier1(context) is False

    def test_suppress_and_clean_cluster_away_from_edits_does_not_fire(self):
        """suppress-and-clean violations not near recently-edited lines are
        just regular suppressions -- deterministic routing handles them."""
        from atdd.coach.commands.judge_call_sites import (
            should_fire_borderline_tier1,
        )

        context = {
            "violations": [
                {
                    "rule_id": "coder.logging.coach-silent-swallow",
                    "severity": 2,
                    "disposition": "suppress-and-clean",
                    "location": "src/foo.py:100",
                },
            ],
            "total_rules": 5,
            "recently_edited_lines": ["src/bar.py:10"],
        }
        assert should_fire_borderline_tier1(context) is False

    def test_no_violations_no_recent_edits_does_not_fire(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_borderline_tier1,
        )

        context = {
            "violations": [],
            "total_rules": 5,
            "recently_edited_lines": [],
        }
        assert should_fire_borderline_tier1(context) is False


# ---------------------------------------------------------------------------
# Call site #3 -- retry-vs-escalate
# ---------------------------------------------------------------------------


class TestShouldFireRetryVsEscalate:
    """``should_fire_retry_vs_escalate`` fires exactly one retry before the
    wall per spec S6.9 #3."""

    def test_fires_when_one_retry_remaining(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_retry_vs_escalate,
        )

        context = {"retry_count": 2, "max_retries": 3}
        assert should_fire_retry_vs_escalate(context) is True

    def test_does_not_fire_when_multiple_retries_left(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_retry_vs_escalate,
        )

        context = {"retry_count": 1, "max_retries": 3}
        assert should_fire_retry_vs_escalate(context) is False

    def test_does_not_fire_at_max_retries(self):
        """At the wall (retry_count == max_retries), escalation already
        happened -- no judge call."""
        from atdd.coach.commands.judge_call_sites import (
            should_fire_retry_vs_escalate,
        )

        context = {"retry_count": 3, "max_retries": 3}
        assert should_fire_retry_vs_escalate(context) is False

    def test_does_not_fire_at_zero(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_retry_vs_escalate,
        )

        context = {"retry_count": 0, "max_retries": 3}
        assert should_fire_retry_vs_escalate(context) is False

    def test_fires_with_higher_max(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_retry_vs_escalate,
        )

        context = {"retry_count": 4, "max_retries": 5}
        assert should_fire_retry_vs_escalate(context) is True


# ---------------------------------------------------------------------------
# Call site #4 -- cross-phase regression
# ---------------------------------------------------------------------------


class TestShouldFireCrossPhaseRegression:
    """``should_fire_cross_phase_regression`` fires when later-phase tier-1
    reveals violations not present at the predecessor phase's exit commit."""

    def test_fires_when_new_violations_in_later_phase(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_cross_phase_regression,
        )

        context = {
            "current_phase": "SMOKE",
            "predecessor_phase": "GREEN",
            "current_violations": [
                {"rule_id": "r1", "location": "a.py:10"},
                {"rule_id": "r2", "location": "b.py:20"},
            ],
            "predecessor_exit_violations": [
                {"rule_id": "r1", "location": "a.py:10"},
            ],
        }
        assert should_fire_cross_phase_regression(context) is True

    def test_does_not_fire_when_no_new_violations(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_cross_phase_regression,
        )

        context = {
            "current_phase": "SMOKE",
            "predecessor_phase": "GREEN",
            "current_violations": [
                {"rule_id": "r1", "location": "a.py:10"},
            ],
            "predecessor_exit_violations": [
                {"rule_id": "r1", "location": "a.py:10"},
            ],
        }
        assert should_fire_cross_phase_regression(context) is False

    def test_does_not_fire_when_no_violations(self):
        from atdd.coach.commands.judge_call_sites import (
            should_fire_cross_phase_regression,
        )

        context = {
            "current_phase": "SMOKE",
            "predecessor_phase": "GREEN",
            "current_violations": [],
            "predecessor_exit_violations": [],
        }
        assert should_fire_cross_phase_regression(context) is False

    def test_does_not_fire_when_current_subset_of_predecessor(self):
        """Current violations are a subset of predecessor -- some were fixed,
        none regressed."""
        from atdd.coach.commands.judge_call_sites import (
            should_fire_cross_phase_regression,
        )

        context = {
            "current_phase": "SMOKE",
            "predecessor_phase": "GREEN",
            "current_violations": [
                {"rule_id": "r1", "location": "a.py:10"},
            ],
            "predecessor_exit_violations": [
                {"rule_id": "r1", "location": "a.py:10"},
                {"rule_id": "r2", "location": "b.py:20"},
            ],
        }
        assert should_fire_cross_phase_regression(context) is False

    def test_fires_when_predecessor_had_no_violations(self):
        """A clean predecessor with any current violations is a pure
        regression."""
        from atdd.coach.commands.judge_call_sites import (
            should_fire_cross_phase_regression,
        )

        context = {
            "current_phase": "SMOKE",
            "predecessor_phase": "GREEN",
            "current_violations": [
                {"rule_id": "r1", "location": "a.py:10"},
            ],
            "predecessor_exit_violations": [],
        }
        assert should_fire_cross_phase_regression(context) is True


# ---------------------------------------------------------------------------
# judgments.jsonl discipline -- no line when predicate does not fire
# ---------------------------------------------------------------------------


def _register_stub(payload: dict) -> str:
    from atdd.coach.commands import judge as judge_mod

    class _StubClient:
        def invoke(self, prompt: str):
            return payload

    judge_mod.register_llm_client("stub-d002-trigger", lambda: _StubClient())
    return "stub-d002-trigger"


@pytest.fixture(autouse=True)
def _isolate_judge_registry():
    from atdd.coach.commands import judge as judge_mod

    snapshot = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    yield
    judge_mod.LLM_REGISTRY.clear()
    judge_mod.LLM_REGISTRY.update(snapshot)


class TestNoJudgmentLineWhenPredicateDoesNotFire:
    """When the trigger predicate returns False, no judgments.jsonl line
    is appended for that call site."""

    def test_borderline_tier1_clean_pass_no_judgment_line(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_borderline_tier1_judge,
        )

        llm = _register_stub({"decision": "pass", "confidence": 0.9, "rationale": "ok"})
        result = invoke_borderline_tier1_judge(
            context={
                "violations": [],
                "total_rules": 5,
                "recently_edited_lines": [],
            },
            llm=llm,
        )
        assert result["fired"] is False
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        assert not log.exists() or log.read_text().strip() == ""

    def test_retry_vs_escalate_early_no_judgment_line(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_retry_vs_escalate_judge,
        )

        llm = _register_stub({"decision": "retry", "reasoning": "worth trying again"})
        result = invoke_retry_vs_escalate_judge(
            context={"retry_count": 1, "max_retries": 3},
            llm=llm,
        )
        assert result["fired"] is False
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        assert not log.exists() or log.read_text().strip() == ""

    def test_cross_phase_no_regression_no_judgment_line(self, repo: Path):
        from atdd.coach.commands.judge_call_sites import (
            invoke_cross_phase_regression_judge,
        )

        llm = _register_stub({
            "decision": "fix_in_place",
            "target_phase": "GREEN",
            "rationale": "minor fix",
        })
        result = invoke_cross_phase_regression_judge(
            context={
                "current_phase": "SMOKE",
                "predecessor_phase": "GREEN",
                "current_violations": [],
                "predecessor_exit_violations": [],
            },
            llm=llm,
        )
        assert result["fired"] is False
        log = repo / ".atdd" / "runtime" / "coach" / "judgments.jsonl"
        assert not log.exists() or log.read_text().strip() == ""
