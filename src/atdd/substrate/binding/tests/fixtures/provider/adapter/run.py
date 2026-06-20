"""Run half of the python-pytest provider contract (contract_version 1.0.0).

Execute discovered implementations inside the materialized workspace instance
with the provider command (``pytest``) and translate the result into the ATDD
violation-output contract (``rule_id`` + location). Uses pytest's JSON-free,
always-available machine signal — the process exit code and the ``--tb=no -q``
summary line — so it needs no pytest plugins beyond core.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

CONTRACT_VERSION = "1.0.0"
RUN_COMMAND = (sys.executable, "-m", "pytest")

# pytest exit codes (pytest.ExitCode) the contract distinguishes.
_EXIT_OK = 0
_EXIT_TESTS_FAILED = 1


@dataclass(frozen=True)
class RunResult:
    """Outcome of running one implementation's tests under the provider."""

    implementation_id: str
    passed: bool
    exit_code: int
    violations: list[dict] = field(default_factory=list)
    stdout: str = ""

    @property
    def ran(self) -> bool:
        """True when pytest actually collected and executed (not a usage error)."""
        return self.exit_code in (_EXIT_OK, _EXIT_TESTS_FAILED)


def _to_violations(exit_code: int, stdout: str, implementation_id: str) -> list[dict]:
    """Translate a failing pytest run into the violation-output contract.

    A passing run yields no violations; a failing run yields one violation whose
    ``rule_id`` is the implementation id, carrying the pytest summary as evidence.
    Location is the implementation root — line-level mapping is the runner wagon's
    job, not the contract's.
    """
    if exit_code == _EXIT_OK:
        return []
    summary = stdout.strip().splitlines()[-1] if stdout.strip() else f"exit {exit_code}"
    return [{"rule_id": implementation_id, "location": ".", "evidence": summary}]


def run_implementation(
    implementation_id: str, test_path: str | Path, *, env: dict | None = None
) -> RunResult:
    """Run pytest over ``test_path`` and return a contract-shaped result.

    ``test_path`` is a file or directory inside the resolved workspace instance.
    The provider command is ``python -m pytest`` so the interpreter that resolved
    the instance is the one that runs it.
    """
    cmd = [*RUN_COMMAND, "--tb=no", "-q", str(test_path)]
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, capture_output=True, text=True, env=env
    )
    stdout = proc.stdout + proc.stderr
    return RunResult(
        implementation_id=implementation_id,
        passed=proc.returncode == _EXIT_OK,
        exit_code=proc.returncode,
        violations=_to_violations(proc.returncode, stdout, implementation_id),
        stdout=stdout,
    )
