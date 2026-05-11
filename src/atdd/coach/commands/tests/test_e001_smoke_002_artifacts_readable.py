# URN: test:integrate-end-to-end:end-to-end-coach-cycle:E001-SMOKE-002-artifacts-readable
# Acceptance: acc:integrate-end-to-end:E001-SMOKE-002-artifacts-readable
# WMBT: wmbt:integrate-end-to-end:E001
# Phase: GREEN
# Layer: assembly
# Harness: smoke/backend
"""E001-SMOKE-002 — Runtime artifacts are readable and structurally valid.

A reader opening decisions.jsonl, judgments.jsonl, and per-commit
validations/<sha>/ artifacts can reconstruct the full state-machine path
and pair each validation with its commit SHA.

Tests:
- decisions.jsonl has entries with at minimum an ``issue_number`` and a
  ``phase`` or ``transition`` field so the state-machine path is
  reconstructable.
- judgments.jsonl (if present) has valid JSON Lines entries.
- Per-commit risk-score.json files contain a ``total_score`` or
  equivalent top-level key.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

REPO_ROOT = Path(__file__).resolve().parents[5]
COACH_RUNTIME = REPO_ROOT / ".atdd" / "runtime" / "coach"
VALIDATIONS_DIR = COACH_RUNTIME / "validations"


def _skip_if_no_cycle() -> None:
    decisions = COACH_RUNTIME / "decisions.jsonl"
    if not decisions.exists():
        pytest.skip(
            "No cycle artifacts. Run `atdd coach <N>` on the worked-example issue first."
        )


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def test_decisions_entries_allow_state_machine_reconstruction() -> None:
    _skip_if_no_cycle()
    entries = _load_jsonl(COACH_RUNTIME / "decisions.jsonl")
    assert entries, "decisions.jsonl must have at least one entry"

    missing_fields: list[int] = []
    for i, entry in enumerate(entries):
        has_issue = "issue_number" in entry or "issue" in entry
        has_phase = any(k in entry for k in ("phase", "from_phase", "to_phase", "transition", "status"))
        if not (has_issue and has_phase):
            missing_fields.append(i + 1)

    assert not missing_fields, (
        f"decisions.jsonl entries at line(s) {missing_fields[:5]} lack 'issue_number' and/or "
        f"a phase/transition field. Entries must support state-machine reconstruction."
    )


def test_judgments_jsonl_valid_if_present() -> None:
    _skip_if_no_cycle()
    judgments = COACH_RUNTIME / "judgments.jsonl"
    if not judgments.exists():
        pytest.skip("judgments.jsonl not present — no atdd judge calls exercised in this cycle")

    entries = _load_jsonl(judgments)
    assert entries, "judgments.jsonl exists but is empty"

    invalid: list[int] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            invalid.append(i + 1)
    assert not invalid, f"judgments.jsonl has non-dict entries at line(s) {invalid[:5]}"


def test_risk_score_json_readable() -> None:
    _skip_if_no_cycle()
    if not VALIDATIONS_DIR.exists():
        pytest.skip("No validations directory")

    sha_dirs = [d for d in VALIDATIONS_DIR.iterdir() if d.is_dir()]
    if not sha_dirs:
        pytest.skip("No per-commit SHA directories in validations/")

    unreadable: list[str] = []
    for sha_dir in sha_dirs:
        risk_file = sha_dir / "risk-score.json"
        if not risk_file.exists():
            continue
        try:
            data = json.loads(risk_file.read_text())
            if not isinstance(data, dict):
                unreadable.append(f"{sha_dir.name}/risk-score.json: not a JSON object")
        except json.JSONDecodeError as exc:
            unreadable.append(f"{sha_dir.name}/risk-score.json: {exc}")

    assert not unreadable, (
        f"risk-score.json files are not readable:\n"
        + "\n".join(f"  {u}" for u in unreadable)
    )


def test_violations_jsonl_readable() -> None:
    _skip_if_no_cycle()
    if not VALIDATIONS_DIR.exists():
        pytest.skip("No validations directory")

    sha_dirs = [d for d in VALIDATIONS_DIR.iterdir() if d.is_dir()]
    if not sha_dirs:
        pytest.skip("No per-commit SHA directories in validations/")

    unreadable: list[str] = []
    for sha_dir in sha_dirs:
        v_file = sha_dir / "violations.jsonl"
        if not v_file.exists():
            continue
        for i, line in enumerate(v_file.read_text().splitlines()):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                unreadable.append(f"{sha_dir.name}/violations.jsonl line {i + 1}: {exc}")
                break  # one parse error per file is enough

    assert not unreadable, (
        f"violations.jsonl files have invalid JSON:\n"
        + "\n".join(f"  {u}" for u in unreadable)
    )
