# URN: component:govern-lifecycle:enforcement-substrate:risk_score_unit:backend:tests
# Runtime: python
# Purpose: AC E002-UNIT-001 — mixed toolkit and repo violations produce full breakdown.

"""
Unit tests for ``atdd.coach.runtime.risk_score.compute_risk_score``.

Covers acceptance acc:dispatch-validators:E002-UNIT-001-mixed-toolkit-and-repo-breakdown:
  - risk_score.sum == sum(severity for active_violations)
  - by_archetype has non-zero repo and at least one non-zero toolkit archetype
  - by_severity populated with count per level
  - by_disposition populated via bind_rule(rule_id).disposition
  - stale_suppressions count passed through
  - by_archetype.repo sums WMBT-acceptance (sev 4), train-acceptance (sev 4),
    and security-derived (mapped low→2/medium→3/high→4/critical→5)
"""

from __future__ import annotations

import pytest

from atdd.coach.validators._violation import Violation


def _v(rule_id: str, severity: int, location: str = "x.py:1") -> Violation:
    return Violation(
        rule_id=rule_id,
        severity=severity,
        location=location,
        detail="fixture",
    )


# ---------------------------------------------------------------------------
# Import guard — module under test does not exist yet (RED phase)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_rule_cache():
    """Clear the bind_rule cache between tests to avoid cross-contamination."""
    from atdd.coach.utils.rule_binding import clear_cache
    clear_cache()
    yield
    clear_cache()


def _patch_bind_rule(monkeypatch, disposition_map: dict[str, str | None]):
    """Patch bind_rule to return RuleMetadata with the given dispositions."""
    from atdd.coach.utils.rule_binding import RuleMetadata

    def _mock_bind(rule_id: str) -> RuleMetadata:
        disp = disposition_map.get(rule_id)
        return RuleMetadata(
            rule_id=rule_id,
            severity=1,
            description="mock",
            disposition=disp,
        )

    monkeypatch.setattr(
        "atdd.coach.runtime.risk_score.bind_rule", _mock_bind
    )


# ---------------------------------------------------------------------------
# AC: mixed toolkit and repo violations produce full breakdown
# ---------------------------------------------------------------------------


class TestMixedBreakdown:
    """E002-UNIT-001: mixed toolkit + repo violations produce complete breakdown."""

    def test_sum_equals_total_severity(self, monkeypatch):
        from atdd.coach.runtime.risk_score import compute_risk_score

        _patch_bind_rule(monkeypatch, {
            "coder.dead-code.unreachable": "strict",
            "coach.rule-id.grammar": "advisory",
            "repo.acceptance.ledger-shape": "strict",
            "repo.security.session-token": "strict",
        })

        violations = [
            _v("coder.dead-code.unreachable", 3),
            _v("coach.rule-id.grammar", 2),
            _v("repo.acceptance.ledger-shape", 4),
            _v("repo.security.session-token", 5),
        ]

        score = compute_risk_score(violations, stale_suppression_count=0)

        assert score.sum == 3 + 2 + 4 + 5

    def test_by_archetype_has_repo_and_toolkit_slices(self, monkeypatch):
        from atdd.coach.runtime.risk_score import compute_risk_score

        _patch_bind_rule(monkeypatch, {
            "coder.dead-code.unreachable": "strict",
            "repo.acceptance.ledger-shape": "strict",
        })

        violations = [
            _v("coder.dead-code.unreachable", 3),
            _v("repo.acceptance.ledger-shape", 4),
        ]

        score = compute_risk_score(violations, stale_suppression_count=0)

        assert score.by_archetype["repo"] > 0
        assert score.by_archetype["coder"] > 0

    def test_by_severity_counts_per_level(self, monkeypatch):
        from atdd.coach.runtime.risk_score import compute_risk_score

        _patch_bind_rule(monkeypatch, {
            "coder.dead-code.unreachable": "strict",
            "coder.boundaries.cross-wagon": "strict",
            "coach.rule-id.grammar": "advisory",
            "repo.acceptance.ledger-shape": "strict",
            "repo.security.session-token": "strict",
        })

        violations = [
            _v("coder.dead-code.unreachable", 3),
            _v("coder.boundaries.cross-wagon", 3),
            _v("coach.rule-id.grammar", 2),
            _v("repo.acceptance.ledger-shape", 4),
            _v("repo.security.session-token", 5),
        ]

        score = compute_risk_score(violations, stale_suppression_count=0)

        assert score.by_severity["3"] == 2
        assert score.by_severity["2"] == 1
        assert score.by_severity["4"] == 1
        assert score.by_severity["5"] == 1

    def test_by_disposition_counts_per_disposition(self, monkeypatch):
        from atdd.coach.runtime.risk_score import compute_risk_score

        _patch_bind_rule(monkeypatch, {
            "coder.dead-code.unreachable": "strict",
            "coach.rule-id.grammar": "advisory",
            "repo.acceptance.ledger-shape": "strict",
            "tester.smoke.harness-failed": "suppress-and-clean",
        })

        violations = [
            _v("coder.dead-code.unreachable", 3),
            _v("coach.rule-id.grammar", 2),
            _v("repo.acceptance.ledger-shape", 4),
            _v("tester.smoke.harness-failed", 4),
        ]

        score = compute_risk_score(violations, stale_suppression_count=0)

        assert score.by_disposition["strict"] == 2
        assert score.by_disposition["advisory"] == 1
        assert score.by_disposition["suppress-and-clean"] == 1

    def test_stale_suppressions_passed_through(self, monkeypatch):
        from atdd.coach.runtime.risk_score import compute_risk_score

        _patch_bind_rule(monkeypatch, {
            "coder.dead-code.unreachable": "strict",
        })

        violations = [_v("coder.dead-code.unreachable", 3)]

        score = compute_risk_score(violations, stale_suppression_count=7)

        assert score.stale_suppressions == 7

    def test_repo_slice_sums_acceptance_train_and_security(self, monkeypatch):
        """by_archetype.repo sums WMBT-acceptance (sev 4), train-acceptance
        (sev 4), and security-derived (mapped from abuse_case.severity)
        contributions."""
        from atdd.coach.runtime.risk_score import compute_risk_score

        _patch_bind_rule(monkeypatch, {
            "repo.acceptance.wmbt-001": "strict",
            "repo.acceptance.train-002": "strict",
            "repo.security.low-sev": "strict",
            "repo.security.medium-sev": "strict",
            "repo.security.high-sev": "strict",
            "repo.security.critical-sev": "strict",
        })

        violations = [
            _v("repo.acceptance.wmbt-001", 4),       # WMBT: constant 4
            _v("repo.acceptance.train-002", 4),       # train: constant 4
            _v("repo.security.low-sev", 2),           # low → 2
            _v("repo.security.medium-sev", 3),        # medium → 3
            _v("repo.security.high-sev", 4),          # high → 4
            _v("repo.security.critical-sev", 5),      # critical → 5
        ]

        score = compute_risk_score(violations, stale_suppression_count=0)

        assert score.by_archetype["repo"] == 4 + 4 + 2 + 3 + 4 + 5

    def test_empty_violations_zero_score(self, monkeypatch):
        from atdd.coach.runtime.risk_score import compute_risk_score

        _patch_bind_rule(monkeypatch, {})

        score = compute_risk_score([], stale_suppression_count=0)

        assert score.sum == 0
        assert score.by_severity == {}
        assert score.by_archetype["repo"] == 0
        assert score.by_disposition == {}
        assert score.stale_suppressions == 0

    def test_risk_score_to_dict_matches_schema_shape(self, monkeypatch):
        """to_dict() output must contain all required schema keys."""
        from atdd.coach.runtime.risk_score import compute_risk_score

        _patch_bind_rule(monkeypatch, {
            "coder.dead-code.unreachable": "strict",
        })

        violations = [_v("coder.dead-code.unreachable", 3)]
        score = compute_risk_score(
            violations, stale_suppression_count=1, sha="abc1234"
        )

        d = score.to_dict()

        assert "sum" in d
        assert "by_severity" in d
        assert "by_archetype" in d
        assert "by_disposition" in d
        assert "stale_suppressions" in d
        assert d["sha"] == "abc1234"
