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
        "coder.green.urn",
        "coder.green.urn-layer",
        "coder.security.xss",
        "coach.rule-id.binding",
        "coder.dead-code.cycle",
    ])
    def test_accepts_conformant(self, rid):
        assert validate_grammar(rid, ALLOWED) is None, rid

    @pytest.mark.parametrize("rid,reason", [
        ("Green.urn.thing", "uppercase archetype"),
        ("coder.green", "missing rule_name segment"),
        ("frontend.x.y", "archetype not in closed set"),
        ("coder_green_urn", "underscore separator"),
        ("", "empty string"),
        ("coder..thing", "empty middle segment"),
    ])
    def test_rejects_nonconformant(self, rid, reason):
        assert validate_grammar(rid, ALLOWED) is not None, reason

    def test_rejects_non_string(self):
        assert "string" in validate_grammar(123, ALLOWED)  # type: ignore[arg-type]

    def test_multi_segment_convention_handled(self):
        """Multi-segment convention names (e.g. dead-code) split on the dot."""
        assert validate_grammar("coder.dead-code.cycle", ALLOWED) is None
        assert validate_grammar("coder.error-response.bare-string", ALLOWED) is None


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
            "    - id: coder.green.urn\n"
            "      severity: 3\n"
            "      description: hi\n"
        )
        rows = extract_rules(f)
        assert len(rows) == 1
        _, yaml_path, rule = rows[0]
        assert rule["id"] == "coder.green.urn"
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
            "      - id: coder.green.urn\n"
            "        severity: 3\n"
            "        description: hi\n"
            "  other:\n"
            "    rules:\n"
            "      - id: coder.green.urn-layer\n"
            "        severity: 3\n"
            "        description: hi\n"
        )
        rows = extract_rules(f)
        assert sorted(r["id"] for _, _, r in rows) == ["coder.green.urn", "coder.green.urn-layer"]

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
        for rid in [
            "coder.green.urn",
            "coder.security.xss",
            "coder.dead-code.cycle",
        ]:
            assert RULE_ID_PATTERN.match(rid)

    def test_pattern_rejects_uppercase_legacy(self):
        """Legacy flat IDs (uppercase, hyphen-only) must not match the canonical pattern."""
        assert not RULE_ID_PATTERN.match("GREEN-URN-001")
        assert not RULE_ID_PATTERN.match("COVERAGE-CODE-4.1")
