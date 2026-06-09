# URN: test:mediate-worker-decisions:coach-runtime:E012-SMOKE-001-coach-dispatch-drives-fixture-through-one-mediated-decision
# Acceptance: acc:mediate-worker-decisions:E012-SMOKE-001-coach-dispatch-drives-fixture-through-one-mediated-decision
# WMBT: wmbt:mediate-worker-decisions:E012
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E012-SMOKE-001 — the headline end-to-end smoke (issue #1025).

The single ``atdd coach <fixture>`` dispatch drives a REAL fixture issue: the
worker raises a decision, the attached daemon MEDIATES it (verdict or
escalation), and the daemon writes a durable decision RECORD — with no human, no
``cmux send`` and no TUI. This proves the autonomous loop closes end-to-end
through the one command (the seam the closed #966/#967 never composed).

Scope: the loop cannot push the issue past a phase gate — INIT->PLANNED /
PLANNED->RED require the operator approval token by #1017 design — so the headline
asserts a real mediated DECISION RECORD (anti-theater: a durable ledger entry,
not a log line), not a GitHub phase-label advance an unattended run must not make.

Opt-in (needs live cmux + claude); skips cleanly otherwise. The coach exercises
it live and records evidence per docs/smoke-audit.md."""
from __future__ import annotations

import pytest


def test_e012_smoke_001_coach_dispatch_drives_fixture_through_one_mediated_decision():
    from atdd.mediate_worker_decisions.coach_runtime.live_smoke import (
        coach_dispatch_drives_fixture_live_smoke,
        live_smoke_available,
    )

    skip = live_smoke_available()
    if skip:
        pytest.skip(skip)

    evidence = coach_dispatch_drives_fixture_live_smoke()

    # The worker's decision was mediated by the attached daemon (verdict OR
    # escalation) end-to-end via the single command — no human / cmux send / TUI.
    assert evidence["mediated"] in {"verdict", "escalation"}
    assert evidence["no_human_interaction"] is True
    # Anti-theater: a REAL durable decision record was written (not a log line).
    assert evidence["decision_recorded"] is True
    assert isinstance(evidence["record"], dict) and evidence["record"]
