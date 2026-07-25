# URN: test:govern-lifecycle:smoke-execution-gate-satisfiability:E069-SMOKE-001-live-smoke-run-attests-and-opens-the-gate
# Acceptance: acc:govern-lifecycle:E069-SMOKE-001-live-smoke-run-attests-and-opens-the-gate
# WMBT: wmbt:govern-lifecycle:E069
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Smoke: true
# Purpose: The repo's first execution_kind: live_smoke acceptance — drive the #1602
#          attestation chain against real infrastructure so a run OPENS the
#          SMOKE->REFACTOR gate and a non-run leaves it CLOSED.

"""E069-SMOKE-001 — the smoke-execution gate is satisfiable by running smoke.

This file is what makes ``execution_kind: live_smoke`` mean something in this
repo. It is the acceptance's anchored test, so:

* the #1602 pytest hook attests **this run** to the State Store — running this
  file is what produces the evidence the ``SMOKE->REFACTOR`` gate reads for the
  issue whose branch it runs on; and
* the #1151 rule forbids it any self-skip mechanism, so it must run-or-fail;
  there is no environment in which it quietly reports success by not executing.

The subject it exercises is the chain itself, driven by the shipped harness
:mod:`atdd.coach.gate.live_smoke`. "Real infrastructure" for a lifecycle toolkit
is the real ``git`` binary, a real ``pytest`` subprocess, the real ``pytest11``
entry-point discovery a consumer's ``pip install`` activates, the real SQLite
State Store, and the real
:class:`~atdd.coach.gate.smoke_execution_check.SmokeExecutionGateCheck`. None of
it is stubbed here, and the harness has no way to write an attestation itself —
it can only run pytest and then read what the run left behind.

Both directions are asserted from ONE chain run, because either alone is
worthless: a gate that refuses everything satisfies the negative direction and is
useless, and a gate that accepts everything satisfies the positive one and is a
lie. The evidence for both comes back measured, never assumed — which is also
what keeps this acceptance out of reach of E060's constant-evidence rule.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.live_smoke import ACCEPTANCE_URN, smoke_execution_chain

pytestmark = [pytest.mark.smoke]


def test_a_live_smoke_run_attests_its_own_execution_and_opens_the_gate(
    tmp_path: Path,
) -> None:
    """One chain run; both directions asserted from what it actually did.

    Deliberately ONE test function driving the chain in its own body rather than
    three sharing a module-scoped fixture. The attestation hook records the
    ``call`` phase's duration, so work done in a fixture lands in *setup* and the
    record would claim a real 3-second live run took 4 milliseconds — a true
    statement about the wrong thing, and precisely the fast-but-fake shape #1192
    is about. The duration this test attests is the duration of the live chain.
    """
    chain = smoke_execution_chain(tmp_path)

    # -- the run wrote down what it did, in terms a gate can check ------------ #
    assert chain.pytest_returncode == 0, (
        "the probe suite failed, so nothing below describes a healthy chain"
    )
    assert chain.attested_run_count == 1, (
        f"expected exactly the anchored probe to be attested, got "
        f"{chain.attested_run_count} record(s) — an unanchored test must not be "
        f"attested, and a missing record means the hook never reached the run"
    )
    assert chain.attested_outcome == "passed"
    assert chain.attested_duration_s > 0.0, (
        "a run with no measured duration did not execute (#1192)"
    )
    assert chain.attested_execution_kind == "live_smoke"
    assert chain.attested_acceptance_urn == ACCEPTANCE_URN, (
        "the record must name the planner acceptance it discharges, or it is "
        "evidence for nothing in particular"
    )
    assert chain.attested_commit_sha == chain.head_sha, (
        "the attestation must name the commit it exercised, or staleness is "
        "unknowable and yesterday's smoke licenses today's transition"
    )

    # -- and THAT is what opened the gate ------------------------------------ #
    assert not chain.gate_open_before_run, (
        "the gate was already open before smoke ran; if it opens for free then "
        "the assertion below proves nothing"
    )
    assert chain.gate_open_after_run, (
        f"smoke really ran against real infrastructure and the gate still "
        f"refused: {chain.gate_message_after_run}"
    )

    # -- the other direction: a green suite whose smoke never executed ------- #
    # #1076's shape. The outcome is RECORDED rather than absent — an operator
    # must be able to tell "smoke did not execute" from "smoke was never
    # attempted" — and it does not satisfy the gate.
    assert chain.unexecuted_outcomes == ["skipped"], (
        f"the non-execution must be written down, loudly; recorded outcomes were "
        f"{chain.unexecuted_outcomes}"
    )
    assert not chain.gate_open_without_execution, (
        "a live-smoke test that never executed satisfied the smoke gate"
    )
    assert "skipped" in chain.gate_message_without_execution, (
        f"the refusal must name what it saw: {chain.gate_message_without_execution}"
    )


__all__ = ["test_a_live_smoke_run_attests_its_own_execution_and_opens_the_gate"]
