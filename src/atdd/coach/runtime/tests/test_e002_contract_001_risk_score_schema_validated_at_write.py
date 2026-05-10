# URN: component:govern-lifecycle:enforcement-substrate:risk_score_contract:backend:tests
# Runtime: python
# Purpose: AC E002-CONTRACT-001 — schema validation at write time.

"""
Contract tests for ``atdd.coach.runtime.risk_score.write_risk_score``.

Covers acceptance acc:dispatch-validators:E002-CONTRACT-001-risk-score-schema-validated-at-write:
  - Schema validation against risk-score.schema.json runs synchronously at write time
  - On schema violation: write aborted, coach-internal error emitted
  - On success: atomic write to .atdd/runtime/validations/<sha>/risk-score.json
  - All required fields present: sum, by_severity, by_archetype (with repo), by_disposition, stale_suppressions
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atdd.coach.validators._violation import Violation


@pytest.fixture(autouse=True)
def _clear_rule_cache():
    from atdd.coach.utils.rule_binding import clear_cache
    clear_cache()
    yield
    clear_cache()


def _patch_bind_rule(monkeypatch, disposition_map: dict[str, str | None]):
    from atdd.coach.utils.rule_binding import RuleMetadata

    def _mock_bind(rule_id: str) -> RuleMetadata:
        disp = disposition_map.get(rule_id)
        return RuleMetadata(
            rule_id=rule_id,
            severity=1,
            description="mock",
            recipe="",
            introduced_in="",
            source_path="",
            disposition=disp,
        )

    monkeypatch.setattr(
        "atdd.coach.runtime.risk_score.bind_rule", _mock_bind
    )


def _make_score(monkeypatch, **kwargs):
    """Create a RiskScore via compute_risk_score for write tests."""
    from atdd.coach.runtime.risk_score import compute_risk_score

    _patch_bind_rule(monkeypatch, {
        "coder.dead-code.unreachable": "strict",
        "repo.acceptance.ledger-shape": "strict",
    })

    violations = [
        Violation(rule_id="coder.dead-code.unreachable", severity=3, location="x.py:1", detail="test"),
        Violation(rule_id="repo.acceptance.ledger-shape", severity=4, location="y.py:2", detail="test"),
    ]
    return compute_risk_score(
        violations,
        stale_suppression_count=kwargs.get("stale_suppressions", 0),
        sha=kwargs.get("sha", "deadbeef"),
        phase=kwargs.get("phase"),
    )


# ---------------------------------------------------------------------------
# AC: schema validation at write time
# ---------------------------------------------------------------------------


class TestSchemaValidatedWrite:
    """E002-CONTRACT-001: schema validation runs at write time."""

    def test_valid_score_writes_to_disk(self, monkeypatch, tmp_path):
        from atdd.coach.runtime.risk_score import write_risk_score

        score = _make_score(monkeypatch, sha="deadbeef")
        result = write_risk_score(score, sha="deadbeef", runtime_dir=tmp_path)

        assert result.exists()
        data = json.loads(result.read_text())
        assert data["sum"] == 7
        assert data["by_archetype"]["repo"] == 4
        assert "deadbeef" in str(result)

    def test_written_file_contains_all_required_fields(self, monkeypatch, tmp_path):
        from atdd.coach.runtime.risk_score import write_risk_score

        score = _make_score(monkeypatch, sha="abc1234")
        result = write_risk_score(score, sha="abc1234", runtime_dir=tmp_path)

        data = json.loads(result.read_text())
        required = {"sum", "by_severity", "by_archetype", "by_disposition", "stale_suppressions"}
        assert required.issubset(set(data.keys()))
        assert "repo" in data["by_archetype"]

    def test_malformed_score_aborts_write(self, tmp_path):
        """A RiskScore with negative sum (schema violation) must NOT be written."""
        from atdd.coach.runtime.risk_score import RiskScore, write_risk_score

        bad_score = RiskScore(
            sum=-1,
            by_severity={},
            by_archetype={"repo": 0},
            by_disposition={},
            stale_suppressions=0,
        )

        result = write_risk_score(bad_score, sha="bad0000", runtime_dir=tmp_path)

        assert not result.exists()

    def test_no_malformed_file_persisted_on_schema_error(self, tmp_path):
        """Even a partial file must not exist after schema validation failure."""
        from atdd.coach.runtime.risk_score import RiskScore, write_risk_score

        bad_score = RiskScore(
            sum=-1,
            by_severity={},
            by_archetype={"repo": 0},
            by_disposition={},
            stale_suppressions=0,
        )

        write_risk_score(bad_score, sha="bad0000", runtime_dir=tmp_path)

        target = tmp_path / "validations" / "bad0000" / "risk-score.json"
        assert not target.exists()

    def test_atomic_write_no_partial_file_on_schema_error(self, tmp_path):
        """Schema validation runs before any file write — no partial artifact."""
        from atdd.coach.runtime.risk_score import RiskScore, write_risk_score

        bad_score = RiskScore(
            sum=-999,
            by_severity={"1": -1},
            by_archetype={"repo": -5},
            by_disposition={},
            stale_suppressions=0,
        )

        write_risk_score(bad_score, sha="partial1", runtime_dir=tmp_path)

        validations_dir = tmp_path / "validations" / "partial1"
        if validations_dir.exists():
            assert not list(validations_dir.iterdir())

    def test_overwrite_replaces_previous(self, monkeypatch, tmp_path):
        """A second write to the same sha replaces the previous file."""
        from atdd.coach.runtime.risk_score import write_risk_score

        score1 = _make_score(monkeypatch, sha="overwrite")
        write_risk_score(score1, sha="overwrite", runtime_dir=tmp_path)

        score2 = _make_score(monkeypatch, sha="overwrite", stale_suppressions=3)
        result = write_risk_score(score2, sha="overwrite", runtime_dir=tmp_path)

        data = json.loads(result.read_text())
        assert data["stale_suppressions"] == 3
