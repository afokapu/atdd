# URN: component:govern-lifecycle:enforcement-substrate:test_violation:backend:domain
# Runtime: python
# Purpose: Cover Violation dataclass invariants — severity bounds, required fields, serialization.

"""Tests for the Violation dataclass.

Specs covered (see src/atdd/coach/specs/rule-id.spec.md):
- SPEC-COACH-RULEID-0003: severity is integer in [1, 5]
- SPEC-COACH-RULEID-0006: required fields are id, severity, description (description
  is on the RULE, not the violation; on the Violation we require rule_id, severity,
  location, detail).
"""

import pytest

from atdd.coach.validators._violation import Violation


def _ok() -> Violation:
    return Violation(
        rule_id="GREEN-URN-001",
        severity=3,
        location="src/foo.py:1",
        detail="missing URN marker",
    )


class TestSeverity:
    @pytest.mark.parametrize("sev", [1, 2, 3, 4, 5])
    def test_accepts_1_through_5(self, sev):
        v = Violation(rule_id="X-Y-001", severity=sev, location="a:1", detail="d")
        assert v.severity == sev

    @pytest.mark.parametrize("sev", [0, 6, -1, 100])
    def test_rejects_out_of_range(self, sev):
        with pytest.raises(ValueError, match="severity"):
            Violation(rule_id="X-Y-001", severity=sev, location="a:1", detail="d")

    @pytest.mark.parametrize("sev", [1.0, "3", None])
    def test_rejects_non_int(self, sev):
        with pytest.raises(ValueError, match="severity"):
            Violation(rule_id="X-Y-001", severity=sev, location="a:1", detail="d")


class TestRequiredFields:
    def test_empty_rule_id_rejected(self):
        with pytest.raises(ValueError, match="rule_id"):
            Violation(rule_id="", severity=3, location="a:1", detail="d")

    def test_empty_location_rejected(self):
        with pytest.raises(ValueError, match="location"):
            Violation(rule_id="X-Y-001", severity=3, location="", detail="d")


class TestSerialization:
    def test_to_dict_round_trip_keys(self):
        d = _ok().to_dict()
        assert d == {
            "rule_id": "GREEN-URN-001",
            "severity": 3,
            "location": "src/foo.py:1",
            "detail": "missing URN marker",
        }

    def test_to_dict_includes_fix_hint_ref_when_set(self):
        v = Violation(
            rule_id="GREEN-URN-001",
            severity=3,
            location="src/foo.py:1",
            detail="missing URN marker",
            fix_hint_ref="recipe:adapter#step-1",
        )
        assert v.to_dict()["fix_hint_ref"] == "recipe:adapter#step-1"

    def test_to_dict_drops_fix_hint_ref_when_none(self):
        assert "fix_hint_ref" not in _ok().to_dict()

    def test_str_human_readable(self):
        s = str(_ok())
        assert "GREEN-URN-001" in s
        assert "sev=3" in s
        assert "src/foo.py:1" in s
        assert "missing URN marker" in s

    def test_str_includes_fix_hint_ref(self):
        v = Violation(
            rule_id="GREEN-URN-001",
            severity=3,
            location="src/foo.py:1",
            detail="missing URN marker",
            fix_hint_ref="recipe:adapter#step-1",
        )
        assert "recipe:adapter#step-1" in str(v)


class TestImmutability:
    def test_frozen(self):
        v = _ok()
        with pytest.raises(Exception):
            v.severity = 5  # type: ignore[misc]
