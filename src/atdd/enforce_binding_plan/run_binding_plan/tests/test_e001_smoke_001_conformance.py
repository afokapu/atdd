# URN: test:enforce-binding-plan:run-binding-plan:E001-SMOKE-001-conformance
# Acceptance: acc:enforce-binding-plan:E001-SMOKE-001-conformance
# WMBT: wmbt:enforce-binding-plan:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E001-SMOKE-001 — every disposition:bound rule runs end-to-end (V1).

Drives the real ``atdd enforce`` runner over a checkout carrying bound
conventions. The conformance invariant from V1: every bound rule executes its
detector and returns a clean ``[]`` or valid raw v1.1 records — **0** of them
emit exit-2 ``report test missing`` (today the provider CLI hardcodes
``REPORT_TEST`` so only ``coder.logging.print`` is runnable, i.e. 1/26).

RED reason: the ``atdd enforce`` verb is not wired yet, so argparse rejects it
(``invalid choice: 'enforce'``). When the lock-driven runner ships, this flips
green: the conformance run reports every bound detector ran with no
``report test missing``.
"""
from __future__ import annotations

import pytest

from .conftest import VERB_ABSENT, repo_src

pytestmark = pytest.mark.smoke


def test_e001_smoke_001_all_bound_rules_run_end_to_end(run_enforce) -> None:
    # The runner's conformance check iterates the lock's disposition:bound set
    # and confirms each detector is runnable.
    proc = run_enforce(["--conformance"], cwd=repo_src().parent)
    combined = proc.stdout + proc.stderr

    # Load-bearing RED guard: the verb must be a real command, not an argparse
    # rejection (an "invalid choice" would be a false green).
    assert VERB_ABSENT not in combined, (
        "atdd enforce is not wired as a command — conformance cannot run"
    )

    # V1 invariant: no bound rule is unrunnable. The today-failure signature is
    # the provider CLI's exit-2 "report test missing"; conformance must never
    # surface it for any of the bound conventions.
    assert "report test missing" not in combined.lower(), (
        "a bound rule emitted 'report test missing' — provider CLI not generalized "
        "(V1: 0 of 26 must be unrunnable):\n" + combined
    )

    # Conformance over a fully-runnable bound set exits clean.
    assert proc.returncode == 0, (
        f"conformance exited {proc.returncode}, expected 0:\n{combined}"
    )
