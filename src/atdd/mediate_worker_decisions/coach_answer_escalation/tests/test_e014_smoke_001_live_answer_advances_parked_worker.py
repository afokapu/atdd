# URN: test:mediate-worker-decisions:coach-answer-escalation:E014-SMOKE-001-live-answer-advances-parked-worker
# Acceptance: acc:mediate-worker-decisions:E014-SMOKE-001-live-answer-advances-parked-worker
# WMBT: wmbt:mediate-worker-decisions:E014
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E014-SMOKE-001 — a real escalation answered via ``atdd coach answer`` advances the worker.

After a real managed feed_daemon escalates a live worker's blocking decision,
the operator runs ``atdd coach answer`` and the parked worker advances past its
menu (screen-before parked / screen-after answered), the Feed item reaching
resolved with a decision. Drives the real recovery harness; in RED the harness
is unimplemented so this fails.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = [
    pytest.mark.smoke,
    pytest.mark.skipif(
        shutil.which("cmux") is None, reason="live cmux + claude not on PATH"
    ),
]


def test_e014_smoke_001_live_answer_advances_parked_worker():
    from atdd.mediate_worker_decisions.coach_answer_escalation.live_smoke import (
        answer_advances_parked_worker_live_smoke,
    )

    evidence = answer_advances_parked_worker_live_smoke()

    assert evidence["delivered"] is True            # reply delivered via the correct verb
    assert evidence["worker_advanced"] is True      # screen moved past the parked menu
    assert evidence["item_resolved"] is True        # Feed item resolved with a decision
