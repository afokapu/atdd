# URN: test:govern-lifecycle:live-smoke-execution-enforcement:E055-SMOKE-001-real-tester-suite-runs-live-smoke-validator
# Acceptance: acc:govern-lifecycle:E055-SMOKE-001-real-tester-suite-runs-live-smoke-validator
# WMBT: wmbt:govern-lifecycle:E055
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Smoke: true
# Purpose: Eat-own-dog-food — the real `atdd validate tester` surface collects and
#          executes test_live_smoke_execution against this repo's plan/, and the
#          rule resolves from the rebuilt registry (not orphaned, not skipped).

"""E055-SMOKE-001 — verify the live-smoke execution-enforcement substrate is
alive in the *real* toolkit, not skipped.

Issue #1151 ships one validator under ``src/atdd/tester/validators/``:

  - ``test_live_smoke_execution.py`` (live-smoke-acceptance-must-execute)

The GREEN-phase fixtures
(``src/atdd/tester/validators/tests/test_live_smoke_execution_fixtures.py``)
import the pure evaluator directly. This SMOKE test exercises the deployed
surface instead: the validators directory the real suite scans collects the
gate test, it runs and PASSES (not skipped) against the live ``plan/``, and
``bind_rule`` resolves the rule from the rebuilt registry.

The "real infrastructure" for a validator-toolkit feature is the deployed
``atdd`` package plus the live ``plan/`` tree. Nothing here is mocked — every
assertion is against a real subprocess invocation pinned to this worktree.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]

# tests/integration/<this file>  ->  repo root is two parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

_VALIDATOR = "test_live_smoke_execution.py"
_GATE_TEST = "test_every_live_smoke_acceptance_executed"
_RULE_ID = "tester.acceptance-violation.live-smoke-acceptance-must-execute"


def _worktree_env() -> dict:
    """Environment that pins the ``atdd`` package to this worktree."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SRC}{os.pathsep}{existing}" if existing else str(SRC)
    return env


def _validators_dir() -> Path:
    return SRC / "atdd" / "tester" / "validators"


def test_live_smoke_validator_file_ships_under_tester_validators() -> None:
    """The #1151 validator file is present where `atdd validate tester` scans."""
    validator = _validators_dir() / _VALIDATOR
    assert validator.is_file(), f"missing live-smoke validator: {validator}"


def test_real_tester_suite_collects_live_smoke_validator() -> None:
    """`pytest --collect-only` over the validators directory collects the gate
    test (platform-marked tests are included under the suite's selectors)."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(_validators_dir() / _VALIDATOR),
            "--collect-only",
            "-q",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_worktree_env(),
    )
    out = proc.stdout + proc.stderr
    assert f"{_VALIDATOR}::{_GATE_TEST}" in out, (
        f"live-smoke gate test not collected by the real suite scan:\n{out}"
    )


def test_live_smoke_validator_runs_and_passes_not_skipped() -> None:
    """Run the gate validator the way the real suite does — it must report
    PASSED (not SKIPPED) against the live ``plan/`` acceptances."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(_validators_dir() / _VALIDATOR),
            "-v",
            "-p",
            "no:randomly",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_worktree_env(),
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"live-smoke validator did not pass:\n{out}"
    assert _GATE_TEST in out and "PASSED" in out, out
    assert "SKIPPED" not in out, (
        f"the live-smoke gate validator was skipped — it must run, not skip:\n{out}"
    )


def test_bind_rule_resolves_live_smoke_rule_against_real_registry() -> None:
    """`bind_rule` resolves the rule (strict) from the rebuilt registry, proving
    the convention node is not orphaned."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from atdd.coach.utils.rule_binding import bind_rule; "
                f"r = bind_rule({_RULE_ID!r}); "
                "print(r.rule_id, r.severity, r.disposition)"
            ),
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_worktree_env(),
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"bind_rule failed to resolve the rule:\n{out}"
    assert _RULE_ID in out and "strict" in out, out


__all__ = [
    "test_live_smoke_validator_file_ships_under_tester_validators",
    "test_real_tester_suite_collects_live_smoke_validator",
    "test_live_smoke_validator_runs_and_passes_not_skipped",
    "test_bind_rule_resolves_live_smoke_rule_against_real_registry",
]
