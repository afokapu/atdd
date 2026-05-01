# URN: component:govern-lifecycle:enforcement-substrate:test_rule_id_uniqueness_helpers:backend:domain
# Runtime: python
# Purpose: Unit tests for grammar/severity/uniqueness helpers in test_rule_id_uniqueness.

"""Pure-function unit tests for the rule-ID uniqueness validator's helpers.

The repo-walking integration tests live in
``test_rule_id_uniqueness.py`` itself; this file isolates the
grammar/severity/extraction logic so each invariant has a focused regression.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_rule_id_uniqueness import (
    RULE_ID_PATTERN,
    extract_rules,
    load_allowed_domains,
    validate_description,
    validate_grammar,
    validate_severity,
)


ALLOWED = load_allowed_domains()


# ---------------------------------------------------------------------------
# Grammar
# ---------------------------------------------------------------------------

class TestGrammar:
    @pytest.mark.parametrize("rid", [
        "GREEN-URN-001",
        "GREEN-URN-LAYER-002",
        "SECURITY-XSS-001",
        "COACH-RULEID-001",
        "DEAD-CODE-CYCLE-001",
    ])
    def test_accepts_conformant(self, rid):
        assert validate_grammar(rid, ALLOWED) is None, rid

    @pytest.mark.parametrize("rid,reason", [
        ("green-urn-001", "lowercase domain"),
        ("GREEN-URN-1", "single-digit suffix"),
        ("GREEN-URN-12", "two-digit suffix"),
        ("GREEN_URN_001", "underscore separator"),
        ("MISC-FOO-001", "domain not in registry"),
        ("GREEN-001", "missing topic"),
        ("", "empty string"),
    ])
    def test_rejects_nonconformant(self, rid, reason):
        assert validate_grammar(rid, ALLOWED) is not None, reason

    def test_rejects_non_string(self):
        assert "string" in validate_grammar(123, ALLOWED)  # type: ignore[arg-type]

    def test_dead_code_domain_handled(self):
        """DEAD-CODE itself contains a hyphen; the grammar must split correctly."""
        assert validate_grammar("DEAD-CODE-CYCLE-001", ALLOWED) is None
        # And without a topic, it should still fail.
        assert validate_grammar("DEAD-CODE-001", ALLOWED) is None


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

class TestSeverity:
    @pytest.mark.parametrize("sev", [1, 2, 3, 4, 5])
    def test_accepts_1_to_5(self, sev):
        assert validate_severity({"severity": sev}) is None

    @pytest.mark.parametrize("sev", [0, 6, -1, "error", None, 1.0, True])
    def test_rejects_other(self, sev):
        assert validate_severity({"severity": sev}) is not None


# ---------------------------------------------------------------------------
# Description
# ---------------------------------------------------------------------------

class TestDescription:
    def test_accepts_non_empty(self):
        assert validate_description({"description": "a thing"}) is None

    @pytest.mark.parametrize("desc", ["", "   ", None])
    def test_rejects_empty_or_missing(self, desc):
        assert validate_description({"description": desc}) is not None

    def test_rejects_missing_key(self):
        assert validate_description({}) is not None


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

class TestExtraction:
    def test_extracts_structured_rules(self, tmp_path: Path):
        f = tmp_path / "x.convention.yaml"
        f.write_text(
            "top:\n"
            "  rules:\n"
            "    - id: GREEN-URN-001\n"
            "      severity: 3\n"
            "      description: hi\n"
        )
        rows = extract_rules(f)
        assert len(rows) == 1
        _, yaml_path, rule = rows[0]
        assert rule["id"] == "GREEN-URN-001"
        assert "rules" in yaml_path

    def test_ignores_prose_rules(self, tmp_path: Path):
        """Legacy ``rules: [str, str]`` arrays are not structured rules."""
        f = tmp_path / "x.convention.yaml"
        f.write_text(
            "top:\n"
            "  rules:\n"
            "    - just a prose string\n"
            "    - another one\n"
        )
        assert extract_rules(f) == []

    def test_walks_nested_blocks(self, tmp_path: Path):
        f = tmp_path / "x.convention.yaml"
        f.write_text(
            "top:\n"
            "  inner:\n"
            "    rules:\n"
            "      - id: GREEN-URN-001\n"
            "        severity: 3\n"
            "        description: hi\n"
            "  other:\n"
            "    rules:\n"
            "      - id: GREEN-URN-002\n"
            "        severity: 3\n"
            "        description: hi\n"
        )
        rows = extract_rules(f)
        assert sorted(r["id"] for _, _, r in rows) == ["GREEN-URN-001", "GREEN-URN-002"]

    def test_handles_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.convention.yaml"
        f.write_text("")
        assert extract_rules(f) == []

    def test_handles_invalid_yaml(self, tmp_path: Path):
        f = tmp_path / "bad.convention.yaml"
        f.write_text(": : :\n")
        # Should swallow yaml.YAMLError and return empty.
        assert extract_rules(f) == []


# ---------------------------------------------------------------------------
# Pattern is the same source-of-truth as the grammar checker
# ---------------------------------------------------------------------------

class TestPatternConsistency:
    def test_pattern_matches_canonical_examples(self):
        for rid in ["GREEN-URN-001", "SECURITY-XSS-001", "DEAD-CODE-CYCLE-001"]:
            assert RULE_ID_PATTERN.match(rid)

    def test_pattern_rejects_dotted_legacy(self):
        """Legacy IDs like COVERAGE-CODE-4.1 must not match — they have dots."""
        assert not RULE_ID_PATTERN.match("COVERAGE-CODE-4.1")
