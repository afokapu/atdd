"""
Unit tests for atdd.coach.validators.rule_id_emission_extractor.

URN: urn:atdd:test:coach:validators:rule_id_emission_extractor
Issue: #387 — Registry Coherence Validator (Phase 2 helper)

Lives under validators/tests/ so the rule_id literals embedded in test
fixtures don't get scanned by the coherence validator itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.rule_id_emission_extractor import (
    Emission,
    extract_emissions,
    iter_scan_files,
)


pytestmark = [pytest.mark.coach, pytest.mark.platform]


class TestEmissionExtractorPatterns:
    """The three Decision #1 regex patterns extract the expected shapes."""

    def test_pattern_a_matches_violation_kwarg(self, tmp_path: Path):
        f = tmp_path / "v.py"
        f.write_text(
            'from x import Violation\n'
            'v = Violation(rule_id="COACH-PRGATE-0003", severity=4, location="a:1", detail="d")\n'
        )
        emissions = list(extract_emissions(f))
        ids = {e.rule_id for e in emissions}
        assert "COACH-PRGATE-0003" in ids

    def test_pattern_b_matches_constant_with_rule_id_prefix(self, tmp_path: Path):
        f = tmp_path / "c.py"
        f.write_text('RULE_ID_PRGATE_GREEN = "COACH-PRGATE-0003"\n')
        emissions = list(extract_emissions(f))
        assert any(e.rule_id == "COACH-PRGATE-0003" for e in emissions)

    def test_pattern_b_matches_constant_without_rule_id_prefix(self, tmp_path: Path):
        """Decision #1: pattern (b) matches by VALUE shape, not LHS shape.

        These constants must be caught even though the LHS does not contain
        `RULE_ID`: RULE_EMPTY_RENDER, RULE_HARNESS_ERROR, XSS_RULE_ID,
        RULE_DYNAMIC_TRAIN_ID, RULE_ALLOWLIST_MIGRATION.
        """
        f = tmp_path / "c2.py"
        f.write_text(
            'RULE_EMPTY_RENDER = "TESTER-RENDER-001"\n'
            'XSS_RULE_ID = "coder.security.xss"\n'
            'RULE_DYNAMIC_TRAIN_ID = "BOUNDARIES-ROUTE-COVERAGE-003"\n'
        )
        ids = {e.rule_id for e in extract_emissions(f)}
        assert "TESTER-RENDER-001" in ids
        assert "SECURITY-XSS-001" in ids
        assert "BOUNDARIES-ROUTE-COVERAGE-003" in ids

    def test_pattern_c_matches_keyword_arg_in_other_constructors(self, tmp_path: Path):
        """Catch-all `\\brule_id\\s*=\\s*"..."` (e.g. in non-Violation constructors)."""
        f = tmp_path / "c3.py"
        f.write_text(
            'event = build(rule_id="COACH-BABYSIT-001", reason="x")\n'
        )
        ids = {e.rule_id for e in extract_emissions(f)}
        assert "COACH-BABYSIT-001" in ids

    def test_dynamic_emissions_out_of_scope(self, tmp_path: Path):
        """Decision #1: ``rule_id=rule["id"]`` and ``rule_id=p.rule_id`` are
        deferred — they require AST + control-flow analysis."""
        f = tmp_path / "dyn.py"
        f.write_text(
            'event = build(rule_id=rule["id"], reason="x")\n'
            'event = build(rule_id=p.rule_id, reason="x")\n'
        )
        ids = {e.rule_id for e in extract_emissions(f)}
        assert ids == set()

    def test_emission_records_file_and_line(self, tmp_path: Path):
        f = tmp_path / "loc.py"
        f.write_text(
            "# header\n"
            'RULE_X = "COACH-PRGATE-0003"\n'
        )
        emissions = list(extract_emissions(f))
        assert len(emissions) == 1
        e = emissions[0]
        assert isinstance(e, Emission)
        assert e.file_path == f
        assert e.line == 2


class TestScanSurfaceExclusions:
    """Success Criteria: scan ``validators/**/*.py`` + ``coach/commands/**/*.py``;
    exclude ``**/tests/**`` and ``**/fixtures/**``."""

    def test_skips_tests_directory(self, tmp_path: Path):
        root = tmp_path / "validators"
        (root / "tests").mkdir(parents=True)
        (root / "tests" / "test_inner.py").write_text(
            'RULE_X = "COACH-PRGATE-0003"\n'
        )
        files = list(iter_scan_files([root]))
        assert all("tests" not in p.parts for p in files)

    def test_skips_fixtures_directory(self, tmp_path: Path):
        root = tmp_path / "validators"
        (root / "fixtures").mkdir(parents=True)
        (root / "fixtures" / "sample.py").write_text(
            'RULE_X = "COACH-PRGATE-0003"\n'
        )
        files = list(iter_scan_files([root]))
        assert all("fixtures" not in p.parts for p in files)

    def test_includes_validator_files_directly_under_root(self, tmp_path: Path):
        """Validator files are named test_*.py and ARE the production code."""
        root = tmp_path / "validators"
        root.mkdir(parents=True)
        (root / "test_pr_phase_alignment.py").write_text(
            'RULE_X = "COACH-PRGATE-0003"\n'
        )
        (root / "_violation.py").write_text("# helper\n")
        files = list(iter_scan_files([root]))
        names = {p.name for p in files}
        assert "test_pr_phase_alignment.py" in names
        assert "_violation.py" in names
