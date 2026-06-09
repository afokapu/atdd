# URN: test:mediate-worker-decisions:coach-runtime:E012-SMOKE-001-coach-dispatch-drives-fixture-through-one-mediated-decision
# Acceptance: acc:mediate-worker-decisions:E012-SMOKE-001-coach-dispatch-drives-fixture-through-one-mediated-decision
# WMBT: wmbt:mediate-worker-decisions:E012
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E012-SMOKE-001 — the headline end-to-end smoke (issue #1025).

The single ``atdd coach <fixture>`` dispatch drives a REAL fixture issue from
INIT through ONE mediated decision — worker raises a decision, the attached
daemon mediates it (verdict or escalation), and the worker ADVANCES — with no
human, no ``cmux send`` and no TUI. Anti-theater: asserts the worker actually
advanced (lifecycle state changed / a decision was recorded), NOT a log line.

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

    # The decision was mediated by the attached daemon (verdict OR escalation),
    # with no human / cmux send / TUI.
    assert evidence["mediated"] in {"verdict", "escalation"}
    assert evidence["no_human_interaction"] is True
    # Anti-theater: the worker actually ADVANCED — recorded state changed, not a log.
    assert evidence["advanced"] is True
    assert evidence["state_before"] != evidence["state_after"]
