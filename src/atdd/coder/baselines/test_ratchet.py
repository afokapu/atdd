# URN: component:govern-lifecycle:enforcement-substrate:test_ratchet:backend:domain
# Runtime: python
# Purpose: Cover RatchetBaseline structured + opaque code paths (SPEC-CODER-RATCHET-0001..0006).

"""Tests for RatchetBaseline.

Covers both:
- Legacy opaque-violations path (sequences of dicts/strings) — unchanged.
- New structured `Violation` path (issue #340) — additive persistence to
  the sibling ``coder.violations.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from atdd.coach.validators._violation import Violation
from atdd.coder.baselines.ratchet import (
    RatchetBaseline,
    default_baseline_path,
    default_structured_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def baseline_path(tmp_path: Path) -> Path:
    return tmp_path / ".atdd" / "baselines" / "coder.yaml"


@pytest.fixture
def structured_path(baseline_path: Path) -> Path:
    return default_structured_path(baseline_path)


@pytest.fixture
def ratchet(baseline_path: Path) -> RatchetBaseline:
    return RatchetBaseline(baseline_path)


def _v(rule_id: str = "GREEN-URN-001", severity: int = 3, **kw: Any) -> Violation:
    return Violation(
        rule_id=rule_id,
        severity=severity,
        location=kw.get("location", "src/foo.py:1"),
        detail=kw.get("detail", "missing URN marker"),
        fix_hint_ref=kw.get("fix_hint_ref"),
    )


# ===========================================================================
# Path resolution
# ===========================================================================

class TestPaths:
    def test_default_baseline_path(self, tmp_path):
        p = default_baseline_path(tmp_path)
        assert p == tmp_path / ".atdd" / "baselines" / "coder.yaml"

    def test_default_structured_path(self, tmp_path):
        bp = default_baseline_path(tmp_path)
        sp = default_structured_path(bp)
        assert sp == tmp_path / ".atdd" / "baselines" / "coder.violations.yaml"

    def test_structured_path_attr(self, ratchet, structured_path):
        assert ratchet.structured_path == structured_path


# ===========================================================================
# Legacy opaque path — back-compat must hold (SPEC-CODER-RATCHET-0001..0005)
# ===========================================================================

class TestLegacyOpaqueViolations:
    def test_zero_violations_no_baseline_passes(self, ratchet):
        ratchet.assert_no_regression("v1", current_count=0)

    def test_auto_seed_on_first_run(self, ratchet, baseline_path):
        with pytest.warns(UserWarning, match="Auto-seeded"):
            ratchet.assert_no_regression("v1", current_count=4, violations=["a", "b", "c", "d"])
        assert baseline_path.is_file()
        assert ratchet.get("v1") == 4

    def test_regression_fails(self, ratchet):
        ratchet.save({"v1": 2})
        with pytest.raises(pytest.fail.Exception, match="Regression"):
            ratchet.assert_no_regression("v1", current_count=5, violations=["a"] * 5)

    def test_improvement_warns(self, ratchet):
        ratchet.save({"v1": 5})
        with pytest.warns(UserWarning, match="improved"):
            ratchet.assert_no_regression("v1", current_count=2, violations=["a", "b"])

    def test_holding_steady_passes(self, ratchet):
        ratchet.save({"v1": 3})
        ratchet.assert_no_regression("v1", current_count=3, violations=["a", "b", "c"])

    def test_opaque_violations_do_not_create_structured_file(
        self, ratchet, structured_path
    ):
        """Pre-#340 callers pass list[dict] or list[str]. Must not write coder.violations.yaml."""
        ratchet.save({"v1": 5})
        ratchet.assert_no_regression(
            "v1",
            current_count=2,
            violations=[{"file": "a.py", "line": 1}, "raw string"],
        )
        assert not structured_path.exists()


# ===========================================================================
# Structured path — SPEC-CODER-RATCHET-0006
# ===========================================================================

class TestStructuredViolations:
    def test_structured_violations_persisted(self, ratchet, structured_path):
        violations = [
            _v("GREEN-URN-001", 3, location="src/a.py:1"),
            _v("GREEN-URN-002", 3, location="src/b.py:1"),
        ]
        ratchet.save({"v1": 5})  # so we don't auto-seed
        ratchet.assert_no_regression("v1", current_count=2, violations=violations)
        assert structured_path.is_file()
        data = yaml.safe_load(structured_path.read_text())
        assert "v1" in data
        assert len(data["v1"]) == 2
        assert data["v1"][0]["rule_id"] == "GREEN-URN-001"
        assert data["v1"][0]["severity"] == 3
        assert data["v1"][0]["location"] == "src/a.py:1"

    def test_structured_violations_round_trip_via_load(self, ratchet):
        ratchet.save({"v1": 5})
        ratchet.assert_no_regression(
            "v1",
            current_count=1,
            violations=[_v(fix_hint_ref="recipe:adapter#step-1")],
        )
        loaded = ratchet.load_structured()
        assert loaded["v1"][0]["fix_hint_ref"] == "recipe:adapter#step-1"

    def test_empty_violations_clears_prior_entry(self, ratchet, structured_path):
        ratchet.save({"v1": 5, "v2": 5})
        ratchet.assert_no_regression("v1", current_count=1, violations=[_v()])
        ratchet.assert_no_regression("v2", current_count=1, violations=[_v("GREEN-URN-002")])
        # Now v1 reports clean → entry removed, v2 entry remains.
        ratchet.assert_no_regression("v1", current_count=0, violations=[])
        loaded = ratchet.load_structured()
        assert "v1" not in loaded
        assert "v2" in loaded

    def test_file_removed_when_all_entries_clear(self, ratchet, structured_path):
        ratchet.save({"v1": 5})
        ratchet.assert_no_regression("v1", current_count=1, violations=[_v()])
        assert structured_path.is_file()
        ratchet.assert_no_regression("v1", current_count=0, violations=[])
        assert not structured_path.exists()

    def test_per_validator_entries_isolated(self, ratchet):
        ratchet.save({"v1": 5, "v2": 5})
        ratchet.assert_no_regression("v1", current_count=1, violations=[_v("GREEN-URN-001")])
        ratchet.assert_no_regression("v2", current_count=1, violations=[_v("SECURITY-XSS-001", 5)])
        loaded = ratchet.load_structured()
        assert loaded["v1"][0]["rule_id"] == "GREEN-URN-001"
        assert loaded["v2"][0]["rule_id"] == "SECURITY-XSS-001"
        assert loaded["v2"][0]["severity"] == 5

    def test_structured_persists_even_on_regression_fail(self, ratchet, structured_path):
        """Regression must still record what was found — failure-mode forensics."""
        ratchet.save({"v1": 1})
        with pytest.raises(pytest.fail.Exception):
            ratchet.assert_no_regression(
                "v1",
                current_count=3,
                violations=[_v("GREEN-URN-001"), _v("GREEN-URN-002"), _v("GREEN-URN-003")],
            )
        loaded = ratchet.load_structured()
        assert len(loaded["v1"]) == 3

    def test_load_structured_missing_file(self, ratchet):
        assert ratchet.load_structured() == {}

    def test_mixed_structured_and_opaque_keeps_only_structured(self, ratchet):
        """If a caller passes a mixed list, only the structured items are persisted."""
        ratchet.save({"v1": 5})
        ratchet.assert_no_regression(
            "v1",
            current_count=2,
            violations=[_v("GREEN-URN-001"), {"opaque": True}],
        )
        loaded = ratchet.load_structured()
        assert len(loaded["v1"]) == 1
        assert loaded["v1"][0]["rule_id"] == "GREEN-URN-001"
