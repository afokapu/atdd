# URN: test:govern-lifecycle:hermetic-integration-execution-kind:E005-SMOKE-001-real-tester-suite-runs-both-validators
# Acceptance: acc:govern-lifecycle:E005-SMOKE-001-real-tester-suite-runs-both-validators
# WMBT: wmbt:govern-lifecycle:E005
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Smoke: true
# Purpose: Eat-own-dog-food — the real `atdd validate tester` suite collects and
#          executes both #690 hermetic validators against this repo's plan/.

"""E005-SMOKE-001 — verify the hermetic-integration substrate is alive in the
*real* toolkit, not skipped.

Issue #690 ships two validators under ``src/atdd/tester/validators/``:

  - ``test_hermetic_integration_contract.py``  (hermetic-fake-must-declare-contract)
  - ``test_hermetic_live_smoke_pairing.py``    (hermetic-live-smoke-required-...)

The GREEN-phase RED fixtures
(``src/atdd/tester/validators/tests/test_hermetic_integration_fixtures.py``)
import the pure evaluators directly and assert behaviour in isolation. This
SMOKE test instead exercises the deployed CLI surface:

  1. The exact validators directory that ``atdd validate tester`` scans
     collects BOTH new validator files under the real ``-m "not github_api"``
     filter (not deselected, not skipped).
  2. ``python -m atdd validate tester --local --skip-api`` runs end-to-end on
     this repo, writes its diagnostics artifact, and reports a real pass/fail
     verdict against the live ``plan/`` acceptances.
  3. Both hermetic validators execute and PASS (the verdict against real
     ``plan/`` is honest — no offenders today) and neither appears in the
     diagnostics ``findings`` list.

No HTTP/DB infrastructure is involved: the "real infrastructure" for a
validator-toolkit feature is the deployed ``atdd`` CLI plus the live
``plan/`` tree. Nothing here is mocked — every assertion is against a real
subprocess invocation.

NOTE: This is true eat-own-dog-food coverage — it requires the ``atdd``
package on the path to BE this worktree (the branch under test). The
subprocesses below pin that by invoking ``python -m atdd`` with the
worktree ``src/`` prepended to ``PYTHONPATH``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.smoke]

# tests/integration/<this file>  ->  repo root is two parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

_CONTRACT_VALIDATOR = "test_hermetic_integration_contract.py"
_PAIRING_VALIDATOR = "test_hermetic_live_smoke_pairing.py"
_CONTRACT_TEST = "test_no_undeclared_hermetic_fakes"
_PAIRING_TEST = "test_hermetic_live_smoke_required_is_paired"


def _worktree_env() -> dict:
    """Environment that pins the ``atdd`` package to this worktree."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SRC}{os.pathsep}{existing}" if existing else str(SRC)
    return env


def _validators_dir() -> Path:
    """The tester-validators directory `atdd validate tester` scans."""
    return SRC / "atdd" / "tester" / "validators"


def test_both_hermetic_validator_files_ship_under_tester_validators() -> None:
    """Both #690 validator files are present in the directory the real
    ``atdd validate tester`` suite scans."""
    validators = _validators_dir()
    contract = validators / _CONTRACT_VALIDATOR
    pairing = validators / _PAIRING_VALIDATOR
    assert contract.is_file(), f"missing hermetic validator: {contract}"
    assert pairing.is_file(), f"missing hermetic validator: {pairing}"


def test_real_tester_suite_collects_both_hermetic_validators() -> None:
    """`pytest --collect-only` over the exact validators directory — with the
    same ``-m "not github_api"`` selector `atdd validate tester` applies —
    collects both hermetic validator tests (not deselected, not skipped)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(_validators_dir()),
            "--collect-only",
            "-q",
            "-m",
            "not github_api",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_worktree_env(),
    )
    out = proc.stdout + proc.stderr
    assert f"{_CONTRACT_VALIDATOR}::{_CONTRACT_TEST}" in out, (
        f"hermetic-fake validator not collected by the real suite scan:\n{out}"
    )
    assert f"{_PAIRING_VALIDATOR}::{_PAIRING_TEST}" in out, (
        f"hermetic-pairing validator not collected by the real suite scan:\n{out}"
    )


def test_both_hermetic_validators_run_and_pass_not_skipped() -> None:
    """Run both validators verbosely the way the real suite does — each must
    report PASSED (not SKIPPED) against the live ``plan/`` acceptances."""
    validators = _validators_dir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(validators / _CONTRACT_VALIDATOR),
            str(validators / _PAIRING_VALIDATOR),
            "-v",
            "-m",
            "not github_api",
            "-p",
            "no:randomly",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_worktree_env(),
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"hermetic validators did not pass:\n{out}"
    assert _CONTRACT_TEST in out and "PASSED" in out, out
    assert _PAIRING_TEST in out, out
    assert "SKIPPED" not in out, (
        f"a hermetic validator was skipped — it must run, not skip:\n{out}"
    )
    # Both verdicts are honest passes against the real plan/ tree.
    assert "2 passed" in out, out


def test_atdd_validate_tester_runs_end_to_end_with_real_verdict() -> None:
    """`atdd validate tester --local --skip-api` runs the real tester suite
    on this repo, writes its diagnostics artifact, and the hermetic validators
    produce a clean verdict (no findings) against the live ``plan/``."""
    proc = subprocess.run(
        [sys.executable, "-m", "atdd", "validate", "tester", "--local", "--skip-api"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_worktree_env(),
    )
    out = proc.stdout + proc.stderr

    diag_path = REPO_ROOT / ".atdd" / "diagnostics" / "validation" / "tester.yaml"
    assert diag_path.is_file(), (
        f"atdd validate tester wrote no diagnostics artifact:\n{out}"
    )
    diag = yaml.safe_load(diag_path.read_text(encoding="utf-8"))

    # The run targeted THIS repo's tester/validators tree.
    invocation = diag["run"]["invocation"]
    assert "tester/validators" in invocation or "tester\\validators" in invocation, (
        f"validate tester did not scan the tester/validators tree: {invocation}"
    )

    # A real pass/fail verdict was produced — the suite executed, not aborted.
    outcome = diag["run"]["outcome"]
    assert outcome["passed"] >= 1, f"tester suite produced no passes: {outcome}"

    # The hermetic validators are not offenders — neither appears in findings,
    # i.e. they ran and reported a PASS verdict against the live plan/.
    hermetic_findings = [
        f
        for f in (diag.get("findings") or [])
        if _CONTRACT_VALIDATOR in str(f.get("validator_path", ""))
        or _PAIRING_VALIDATOR in str(f.get("validator_path", ""))
    ]
    assert hermetic_findings == [], (
        f"hermetic validators reported findings: {hermetic_findings}"
    )

    # Conditional contract (acceptance then-clause): any hermetic offender must
    # carry a fix_hint naming the hermetic: block field to add. Vacuously true
    # while the verdict is clean, but the contract is asserted, not assumed.
    for finding in hermetic_findings:
        raw = str(finding.get("raw_message", ""))
        assert "fix_hint" in raw and "hermetic" in raw, (
            f"hermetic finding lacks an actionable fix_hint: {finding}"
        )


__all__ = [
    "test_both_hermetic_validator_files_ship_under_tester_validators",
    "test_real_tester_suite_collects_both_hermetic_validators",
    "test_both_hermetic_validators_run_and_pass_not_skipped",
    "test_atdd_validate_tester_runs_end_to_end_with_real_verdict",
]
