# URN: test:govern-lifecycle:freeze-coach-core-typed-api-and-phase-machine:E035-SMOKE-001-real-import-purity-and-yaml-load
# Acceptance: acc:govern-lifecycle:E035-SMOKE-001-real-import-purity-and-yaml-load
# WMBT: wmbt:govern-lifecycle:E035
# Phase: RED
# Layer: backend.integration
"""AC-SMOKE-001 — a real interpreter subprocess importing ``atdd.coach.core``
does not pull ``subprocess`` into ``sys.modules`` (Coach-core is pure / no I/O at
import time), the public import line succeeds, and the real on-disk
``phase_machine.convention.yaml`` loads into a nine-phase mapping.

Drives the actual package + filesystem through a child interpreter — no stub.

RED state: ``atdd.coach.core`` does not exist, so the subprocess exits non-zero
and the YAML is absent.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root

pytestmark = pytest.mark.coach

REPO_ROOT = find_repo_root()
SRC = REPO_ROOT / "src"
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
PHASE_MACHINE_YAML = ATDD_PKG_DIR / "coach" / "conventions" / "phase_machine.convention.yaml"

_PURITY_SNIPPET = (
    "import sys\n"
    "import atdd.coach.core\n"
    "from atdd.coach.core import (next_transition, evaluate_evidence,\n"
    "    review_phase_output, merge_readiness, escalation_for)\n"
    "assert 'subprocess' not in sys.modules, 'coach.core leaked subprocess at import'\n"
    "print('OK')\n"
)


def _run_fresh(snippet: str) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(SRC), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    return subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )


def test_fresh_import_does_not_leak_subprocess_and_public_api_imports():
    result = _run_fresh(_PURITY_SNIPPET)
    assert result.returncode == 0, (
        f"fresh import failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "OK" in result.stdout


def test_real_phase_machine_yaml_loads_nine_phases():
    assert PHASE_MACHINE_YAML.exists(), f"missing {PHASE_MACHINE_YAML}"
    data = yaml.safe_load(PHASE_MACHINE_YAML.read_text())
    phases = data["phases"]
    assert set(phases) == {
        "INIT", "PLANNED", "RED", "GREEN", "SMOKE",
        "REFACTOR", "COMPLETE", "BLOCKED", "OBSOLETE",
    }
    # spot-check the canonical INIT→PLANNED edge survives a real load
    assert "PLANNED" in phases["INIT"]["transitions_to"]
