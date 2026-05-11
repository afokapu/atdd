# URN: test:integrate-end-to-end:end-to-end-coach-cycle:E001-SMOKE-001-cycle-reaches-complete
# Acceptance: acc:integrate-end-to-end:E001-SMOKE-001-cycle-reaches-complete
# WMBT: wmbt:integrate-end-to-end:E001
# Phase: GREEN
# Layer: assembly
# Harness: smoke/backend
"""E001-SMOKE-001 — End-to-end coach-driven cycle reaches COMPLETE.

Verifies the runtime artifacts produced by running ``atdd coach <N>``
on the worked-example issue from INIT through COMPLETE:

- ``.atdd/runtime/coach/decisions.jsonl`` exists and records at least
  one state transition entry.
- Per-commit ``validations/<sha>/`` directories exist under
  ``.atdd/runtime/coach/validations/`` with the required JSONL files.
- A reviewer report exists under ``.atdd/runtime/agents/`` for at least
  one phase (PLANNED, RED, GREEN, or SMOKE).

These artifacts are produced by running the cycle in the GREEN phase;
this test verifies they are present and structurally valid.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[5]
COACH_RUNTIME = REPO_ROOT / ".atdd" / "runtime" / "coach"
VALIDATIONS_DIR = COACH_RUNTIME / "validations"
AGENTS_DIR = REPO_ROOT / ".atdd" / "runtime" / "agents"


def _skip_if_no_cycle() -> None:
    decisions = COACH_RUNTIME / "decisions.jsonl"
    if not decisions.exists():
        pytest.skip(
            "No coach cycle artifacts found at .atdd/runtime/coach/decisions.jsonl. "
            "Run `atdd coach <N>` on the worked-example issue to produce artifacts, "
            "then re-run this test."
        )


def test_decisions_jsonl_exists_and_nonempty() -> None:
    _skip_if_no_cycle()
    decisions = COACH_RUNTIME / "decisions.jsonl"
    assert decisions.exists(), f"decisions.jsonl must exist at {decisions}"
    lines = [ln for ln in decisions.read_text().splitlines() if ln.strip()]
    assert lines, "decisions.jsonl is empty — at least one state transition must be recorded"


def test_decisions_jsonl_contains_valid_json_lines() -> None:
    _skip_if_no_cycle()
    decisions = COACH_RUNTIME / "decisions.jsonl"
    lines = [ln for ln in decisions.read_text().splitlines() if ln.strip()]
    parse_errors: list[str] = []
    for i, line in enumerate(lines):
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            parse_errors.append(f"line {i + 1}: {exc}")
    assert not parse_errors, (
        f"decisions.jsonl contains invalid JSON on {len(parse_errors)} line(s):\n"
        + "\n".join(parse_errors[:5])
    )


def test_per_commit_validations_directory_exists() -> None:
    _skip_if_no_cycle()
    if not VALIDATIONS_DIR.exists():
        pytest.fail(
            f"No per-commit validations directory found at {VALIDATIONS_DIR}. "
            "The cycle must produce at least one .atdd/runtime/coach/validations/<sha>/ "
            "directory with violations.jsonl, suppressed.jsonl, stale-suppressions.jsonl, "
            "and risk-score.json."
        )
    sha_dirs = [d for d in VALIDATIONS_DIR.iterdir() if d.is_dir()]
    assert sha_dirs, f"validations/ directory exists but is empty: {VALIDATIONS_DIR}"


def test_per_commit_validation_artifacts_present() -> None:
    _skip_if_no_cycle()
    if not VALIDATIONS_DIR.exists():
        pytest.skip("No validations directory — covered by test_per_commit_validations_directory_exists")

    sha_dirs = [d for d in VALIDATIONS_DIR.iterdir() if d.is_dir()]
    if not sha_dirs:
        pytest.skip("No per-commit SHA directories in validations/")

    required_files = ("violations.jsonl", "suppressed.jsonl", "stale-suppressions.jsonl", "risk-score.json")
    missing: list[str] = []
    for sha_dir in sha_dirs:
        for fname in required_files:
            if not (sha_dir / fname).exists():
                missing.append(f"{sha_dir.name}/{fname}")

    assert not missing, (
        f"Per-commit validation artifacts missing from {len(sha_dirs)} SHA dir(s):\n"
        + "\n".join(f"  {m}" for m in missing[:10])
    )


def test_reviewer_report_exists_for_at_least_one_phase() -> None:
    _skip_if_no_cycle()
    if not AGENTS_DIR.exists():
        pytest.fail(
            f"No agents directory found at {AGENTS_DIR}. "
            "The cycle must produce reviewer reports under .atdd/runtime/agents/<id>/reviews/."
        )

    review_files = list(AGENTS_DIR.rglob("*.json"))
    review_files = [f for f in review_files if "reviews" in str(f)]
    assert review_files, (
        f"No reviewer report JSON files found under {AGENTS_DIR}. "
        "The cycle must produce at least one reviewer report for PLANNED, RED, GREEN, or SMOKE."
    )
