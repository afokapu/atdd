# URN: test:govern-lifecycle:phase-aware-coverage:E081-INTEGRATION-001-validators-skip-pre-red-trains
# Acceptance: acc:govern-lifecycle:E081-SMOKE-001-validators-consult-the-owning-phase
# WMBT: wmbt:govern-lifecycle:E081
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E081-INTEGRATION-001 — the three validators themselves, against a real repo.

The unit test pins the `coverage_is_due` decision; this one proves the three
validators actually consult it. They resolve `REPO_ROOT` at MODULE IMPORT time,
so each case runs pytest in a subprocess with `ATDD_REPO_ROOT` pointed at a
freshly built consumer repo — the same way the toolkit's own CI reaches them.

Guards a specific trap: `test_train_route_smoke_coverage.py` carries the gap
comprehension TWICE — once in `scan_train_route_smoke_coverage` (the baseline
registration entrypoint) and once in the test function. Patching only the first
leaves the validator failing while looking fixed (#1920).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_SRC = Path(__file__).resolve().parents[4]

TRAIN_ID = "train:issue-lifecycle:brand-new"
VALIDATORS = (
    "test_train_completeness.py",
    "test_train_e2e_existence.py",
    "test_train_route_smoke_coverage.py",
)


def _build_repo(root: Path, phase: str) -> Path:
    (root / ".atdd" / "state").mkdir(parents=True)
    (root / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\nthemes:\n  0: commons\n", encoding="utf-8"
    )
    (root / "contracts").mkdir()
    (root / "plan" / "_trains" / "issue-lifecycle").mkdir(parents=True)
    (root / "plan" / "_trains.yaml").write_text(yaml.safe_dump({
        "trains": {"issue-lifecycle": {"nominal": [{
            "train_id": TRAIN_ID, "description": "authored before RED",
            "path": "plan/_trains/issue-lifecycle/brand-new.yaml",
            "wagons": ["some-wagon"], "category": "nominal",
        }]}}
    }), encoding="utf-8")
    if phase:
        from atdd.state.db import connect, init_state_store
        from atdd.state.work_item_writer import create_work_item

        conn = connect(init_state_store(start=root))
        try:
            create_work_item(conn, "owning-item", state=phase,
                             data={"title": "the owning issue", "train": TRAIN_ID})
        finally:
            conn.close()
    return root


def _run_validators(repo: Path):
    env = {**os.environ, "ATDD_REPO_ROOT": str(repo), "PYTHONPATH": str(_SRC)}
    targets = [str(_SRC / "atdd" / "tester" / "validators" / v) for v in VALIDATORS]
    return subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q", "-p", "no:randomly", "--no-header"],
        cwd=str(repo), env=env, capture_output=True, text=True, timeout=300,
    )


@pytest.mark.parametrize("phase", ["INIT", "PLANNED"])
def test_a_pre_red_train_raises_no_coverage_violation(tmp_path, phase):
    result = _run_validators(_build_repo(tmp_path, phase))
    assert result.returncode == 0, (
        f"a train owned by a {phase} issue must not be failed for missing tests "
        f"RED has not written yet:\n{result.stdout[-3000:]}"
    )


@pytest.mark.parametrize("phase", ["RED", "GREEN"])
def test_a_train_at_red_or_later_still_fails(tmp_path, phase):
    result = _run_validators(_build_repo(tmp_path, phase))
    assert result.returncode != 0, (
        f"a train at {phase} with no e2e/ is a real gap and must still fail"
    )


def test_an_unmapped_train_still_fails(tmp_path):
    result = _run_validators(_build_repo(tmp_path, ""))
    assert result.returncode != 0, "an untracked train must fail closed"
