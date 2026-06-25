# URN: test:validate-conventions:differential-catch-matrix-harness:E029-RED-001-catch-matrix
# Acceptance: acc:validate-conventions:E027-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E028-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E029-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E030-SMOKE-001-seed
# Acceptance: acc:validate-conventions:E031-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E029
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""#1212 differential catch-matrix harness — runs BOTH suites per seeded fault on
identical input and records the catch-matrix cell. This is the measurement that
decides better/worse (parity / improvement / regression / false-positive)."""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.validators.conventions._support import catch_matrix as CM


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


@pytest.fixture(scope="module")
def cells():
    return CM.run_matrix(_repo_root())


# E027 — fault corpus exists (seeded; expands to one per legacy rule)
def test_fault_corpus_is_seeded() -> None:
    assert CM.CASES, "no fault cases in the corpus"
    for c in CM.CASES:
        assert c.legacy_target and (c.patch or c.tempfile), f"case {c.name} lacks legacy target / fault"


# E028 — both suites run per fault
def test_both_suites_run_per_fault(cells) -> None:
    assert len(cells) == len(CM.CASES)
    for c in cells:
        assert isinstance(c.legacy_caught, bool) and isinstance(c.convention_caught, bool), \
            f"{c.name}: a suite did not run"


# E029 — every fault yields a classified catch-matrix cell
def test_every_fault_has_matrix_cell(cells) -> None:
    valid = {"both", "convention-only", "legacy-only", "neither"}
    for c in cells:
        assert c.verdict in valid, f"{c.name}: unclassified cell {c.verdict}"


# E030 — clean-repo false-positive check
def test_no_clean_repo_false_positive(cells) -> None:
    fps = [c.name for c in cells if c.clean_convention_flags]
    assert not fps, f"convention flags the clean baseline (false positives): {fps}"


# E031 — gap report quantifies the matrix
def test_gap_report_quantifies_matrix() -> None:
    report = _repo_root() / "docs" / "validator-parity" / "catch-matrix.md"
    assert report.exists(), f"catch-matrix report not found at {report}"
    text = report.read_text(encoding="utf-8")
    for marker in ("parity (both)", "convention-only", "legacy-only",
                   "clean-repo false positives"):
        assert marker in text, f"catch-matrix report missing quantifier: {marker!r}"
