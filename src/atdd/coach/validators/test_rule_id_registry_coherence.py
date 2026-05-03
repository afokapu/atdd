# URN: component:govern-lifecycle:enforcement-substrate:rule_id_registry_coherence:backend:domain
# Runtime: python
# Purpose: Surface emissions whose rule_id is not declared in any convention rules: block.

"""
Coach validator for rule-id registry coherence (issue #387).

Walks production validator + command source, extracts rule_id emissions via
three regex patterns (Decision #1), and cross-checks against the registry
built from every ``*.convention.yaml``. Drift surfaces as plain text:

  - permissive mode (default)     → WARN, exit 0
  - ``--strict-coherence``        → ERROR, exit 1

Decision #2: this validator does NOT emit ``Violation`` records for drift —
drift is a config issue, not a runtime violation. Plain text avoids
meta-recursion (a validator emitting violations about emissions).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, List, Tuple

import pytest

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_id_registry import build_registry
from atdd.coach.validators.rule_id_emission_extractor import (
    EMISSION_PATTERNS,
    Emission,
    extract_emissions,
    iter_scan_files,
)


pytestmark = [pytest.mark.coach, pytest.mark.platform]


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent

# Production scan surface (Decision #4):
#   validators/**/*.py + coach/commands/**/*.py
#   exclude:  **/tests/**, **/fixtures/**, test_*.py
_SCAN_ROOTS_REL = (
    ("coach", "validators"),
    ("coder", "validators"),
    ("tester", "validators"),
    ("planner", "validators"),
    ("coach", "commands"),
)


def _scan_roots() -> List[Path]:
    """Return absolute paths to every production scan root (toolkit + repo checkout)."""
    repo_src = find_repo_root() / "src" / "atdd"
    out: List[Path] = []
    for parts in _SCAN_ROOTS_REL:
        for base in (ATDD_PKG_DIR, repo_src):
            cand = base.joinpath(*parts)
            if cand.is_dir():
                out.append(cand)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
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

    def test_pattern_b_matches_constant_with_RULE_ID_prefix(self, tmp_path: Path):
        f = tmp_path / "c.py"
        f.write_text('RULE_ID_PRGATE_GREEN = "COACH-PRGATE-0003"\n')
        emissions = list(extract_emissions(f))
        assert any(e.rule_id == "COACH-PRGATE-0003" for e in emissions)

    def test_pattern_b_matches_constant_without_RULE_ID_prefix(self, tmp_path: Path):
        """Decision #1: pattern (b) matches by VALUE shape, not LHS shape.

        These constants must be caught even though the LHS does not contain
        `RULE_ID`: RULE_EMPTY_RENDER, RULE_HARNESS_ERROR, XSS_RULE_ID,
        RULE_DYNAMIC_TRAIN_ID, RULE_ALLOWLIST_MIGRATION.
        """
        f = tmp_path / "c2.py"
        f.write_text(
            'RULE_EMPTY_RENDER = "TESTER-RENDER-001"\n'
            'XSS_RULE_ID = "SECURITY-XSS-001"\n'
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
        assert e.file_path == f
        assert e.line == 2


class TestScanSurfaceExclusions:
    """Decision #4: tests, fixtures, and test_*.py files (anywhere) are excluded."""

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

    def test_skips_test_underscore_files_anywhere(self, tmp_path: Path):
        """Pytest discovers tests by filename, not directory; exclusion mirrors that."""
        root = tmp_path / "validators"
        sub = root / "baselines"
        sub.mkdir(parents=True)
        (sub / "test_ratchet.py").write_text(
            'RULE_X = "COACH-PRGATE-0003"\n'
        )
        (sub / "ratchet.py").write_text(
            'RULE_X = "COACH-PRGATE-0003"\n'
        )
        files = list(iter_scan_files([root]))
        names = {p.name for p in files}
        assert "ratchet.py" in names
        assert "test_ratchet.py" not in names


class TestCoherenceValidatorAgainstCurrentMain:
    """Run against the real toolkit source — at least one drift entry must surface."""

    def test_known_unregistered_id_surfaces(self):
        """The seeded drift example from #387: ``COACH-PRGATE-0003`` is declared
        in test_pr_phase_alignment.py but not in any convention rules: block.
        """
        registry = build_registry()
        roots = _scan_roots()
        assert roots, "no production scan roots resolved"
        unregistered: List[Tuple[Path, int, str]] = []
        for f in iter_scan_files(roots):
            for e in extract_emissions(f):
                if e.rule_id not in registry:
                    unregistered.append((e.file_path, e.line, e.rule_id))
        ids = {rid for (_, _, rid) in unregistered}
        # Confirmed seeds from the issue body:
        assert "COACH-PRGATE-0003" in ids


@pytest.mark.coach
def test_rule_id_registry_coherence():
    """Permissive-mode coherence check.

    Default behavior: emit a WARN block listing every emission whose
    rule_id is missing from the registry, then PASS (exit 0).

    Strict mode is opt-in via ``ATDD_STRICT_COHERENCE=1`` (the env var the
    CLI flag `--strict-coherence` sets) — when enabled, drift fails the test.
    """
    registry = build_registry()
    roots = _scan_roots()
    drift: List[Tuple[Path, int, str]] = []
    for f in iter_scan_files(roots):
        for e in extract_emissions(f):
            if e.rule_id not in registry:
                drift.append((e.file_path, e.line, e.rule_id))

    if not drift:
        return  # registry is fully coherent; nothing to surface

    repo_root = find_repo_root()
    lines = [
        f"[WARN] rule_id_registry_coherence: "
        f"{len(drift)} emission(s) reference unregistered rule_id(s):"
    ]
    for fp, ln, rid in sorted(drift):
        try:
            rel = fp.resolve().relative_to(repo_root.resolve())
        except ValueError:
            rel = fp
        lines.append(f"  {rel}:{ln}   {rid}   not in any convention rules: block")
    lines.append("  Run with --strict-coherence to fail CI on this.")

    msg = "\n".join(lines)

    strict = os.environ.get("ATDD_STRICT_COHERENCE") == "1"
    if strict:
        pytest.fail(msg)
    else:
        # Plain-text WARN — visible in pytest -v output but does not fail.
        print("\n" + msg)


__all__ = [
    "EMISSION_PATTERNS",
    "Emission",
    "extract_emissions",
    "iter_scan_files",
]
