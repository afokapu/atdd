"""
Pure-evaluator unit tests for the planner SMOKE-acceptance validator (#681).

Co-located with the planner validator helper tests under
``src/atdd/planner/validators/tests/``. These tests exercise the pure
evaluator directly with synthetic ``(path, dict)`` payloads — no disk I/O,
no plan/ walking, no disposition gate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators._violation import Violation
from atdd.planner.validators.test_wmbt_has_smoke_acceptance import (
    _RULE,
    _SMOKE_URN_RE,
    evaluate_wmbt_smoke_coverage,
    extract_acceptance_urns,
    has_smoke_urn,
)


# ---------------------------------------------------------------------------
# Grammar tests
# ---------------------------------------------------------------------------


def test_smoke_urn_regex_matches_canonical_form():
    assert _SMOKE_URN_RE.match(
        "acc:govern-lifecycle:E003-SMOKE-001-validator-suite"
    )


def test_smoke_urn_regex_accepts_no_slug_form():
    assert _SMOKE_URN_RE.match("acc:integration-hardening:E001-SMOKE-001")


def test_smoke_urn_regex_rejects_unit_urn():
    assert not _SMOKE_URN_RE.match(
        "acc:govern-lifecycle:E003-UNIT-001-rules-grep-finds-both"
    )


def test_smoke_urn_regex_rejects_integration_urn():
    assert not _SMOKE_URN_RE.match(
        "acc:govern-lifecycle:E003-INTEGRATION-001-planner-fires"
    )


# ---------------------------------------------------------------------------
# extract_acceptance_urns
# ---------------------------------------------------------------------------


def test_extract_acceptance_urns_from_identity_dict():
    data = {
        "acceptances": [
            {"identity": {"urn": "acc:w:E001-UNIT-001-a"}},
            {"identity": {"urn": "acc:w:E001-SMOKE-001-b"}},
        ]
    }
    assert extract_acceptance_urns(data) == [
        "acc:w:E001-UNIT-001-a",
        "acc:w:E001-SMOKE-001-b",
    ]


def test_extract_acceptance_urns_from_string_form():
    data = {"acceptances": ["acc:w:E001-UNIT-001-a"]}
    assert extract_acceptance_urns(data) == ["acc:w:E001-UNIT-001-a"]


def test_extract_acceptance_urns_skips_missing_urn():
    data = {"acceptances": [{"identity": {}}, {"identity": {"urn": ""}}]}
    assert extract_acceptance_urns(data) == []


def test_extract_acceptance_urns_handles_missing_field():
    assert extract_acceptance_urns({}) == []
    assert extract_acceptance_urns({"acceptances": None}) == []


# ---------------------------------------------------------------------------
# has_smoke_urn
# ---------------------------------------------------------------------------


def test_has_smoke_urn_true_when_any_smoke():
    assert has_smoke_urn([
        "acc:w:E001-UNIT-001-a",
        "acc:w:E001-SMOKE-001-b",
    ]) is True


def test_has_smoke_urn_false_when_none():
    assert has_smoke_urn([
        "acc:w:E001-UNIT-001-a",
        "acc:w:E001-INTEGRATION-002-b",
    ]) is False


def test_has_smoke_urn_false_on_empty():
    assert has_smoke_urn([]) is False


# ---------------------------------------------------------------------------
# evaluate_wmbt_smoke_coverage
# ---------------------------------------------------------------------------


def _wmbt(urn: str, acc_urns: list[str]) -> dict:
    return {
        "urn": urn,
        "acceptances": [{"identity": {"urn": u}} for u in acc_urns],
    }


def test_evaluate_emits_no_violations_when_every_wmbt_has_smoke(tmp_path):
    wmbts = [
        (
            tmp_path / "plan" / "w" / "E001.yaml",
            _wmbt("wmbt:w:E001", [
                "acc:w:E001-UNIT-001-a",
                "acc:w:E001-SMOKE-001-b",
            ]),
        ),
    ]
    violations = evaluate_wmbt_smoke_coverage(wmbts, tmp_path)
    assert violations == []


def test_evaluate_emits_one_violation_per_zero_smoke_wmbt(tmp_path):
    wmbts = [
        (
            tmp_path / "plan" / "w" / "E001.yaml",
            _wmbt("wmbt:w:E001", ["acc:w:E001-UNIT-001-a"]),
        ),
        (
            tmp_path / "plan" / "w" / "E002.yaml",
            _wmbt("wmbt:w:E002", [
                "acc:w:E002-UNIT-001-a",
                "acc:w:E002-INTEGRATION-001-b",
            ]),
        ),
    ]
    violations = evaluate_wmbt_smoke_coverage(wmbts, tmp_path)
    assert len(violations) == 2
    rule_ids = {v.rule_id for v in violations}
    assert rule_ids == {_RULE.rule_id}


def test_evaluate_violation_carries_rule_metadata_and_location(tmp_path):
    yaml_path = tmp_path / "plan" / "w" / "E003.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text("urn: \"wmbt:w:E003\"\nacceptances: []\n")

    wmbts = [(yaml_path, _wmbt("wmbt:w:E003", []))]
    violations = evaluate_wmbt_smoke_coverage(wmbts, tmp_path)

    assert len(violations) == 1
    v = violations[0]
    assert isinstance(v, Violation)
    assert v.rule_id == _RULE.rule_id == "planner.wmbt.must-have-smoke-acceptance"
    assert v.severity == _RULE.severity
    # location must point at the urn: line (1-based) for inline-suppress
    assert v.location.endswith(":1")
    assert "plan/w/E003.yaml" in v.location
    # detail names the WMBT and explains the fix
    assert "wmbt:w:E003" in v.detail
    assert "SMOKE" in v.detail


def test_evaluate_skips_wmbt_that_mixes_in_smoke_among_other_phases(tmp_path):
    wmbts = [
        (
            tmp_path / "plan" / "w" / "E004.yaml",
            _wmbt("wmbt:w:E004", [
                "acc:w:E004-UNIT-001-a",
                "acc:w:E004-INTEGRATION-001-b",
                "acc:w:E004-SMOKE-001-c",
                "acc:w:E004-SMOKE-002-d",
            ]),
        ),
    ]
    violations = evaluate_wmbt_smoke_coverage(wmbts, tmp_path)
    assert violations == []
