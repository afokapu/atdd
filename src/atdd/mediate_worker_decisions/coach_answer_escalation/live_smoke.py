"""Live recovery smoke harness for feature:coach-answer-escalation.

Drives the REAL operational recovery path against a REAL throwaway cmux
workspace running a REAL ``claude`` worker: a managed feed_daemon escalates a
blocking decision, then ``atdd coach answer`` delivers the operator's reply and
we observe the parked worker advance — plus the loud-rejection and status
surfacing behaviours. Each helper returns an evidence dict the SMOKE tests
assert on, and skips cleanly (its own guard) when ``cmux`` is absent.

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations


def answer_advances_parked_worker_live_smoke() -> dict:
    """Induce a real escalation, run ``atdd coach answer``, observe the worker advance."""
    raise NotImplementedError("acc:mediate-worker-decisions:E014-SMOKE-001")


def wrong_label_rejected_live_smoke() -> dict:
    """Run ``atdd coach answer`` with a non-exact label; assert loud reject, no reply."""
    raise NotImplementedError("acc:mediate-worker-decisions:C009-SMOKE-001")


def status_surfaces_then_omits_live_smoke() -> dict:
    """Assert ``atdd coach status`` lists the unanswered escalation, then omits it once answered."""
    raise NotImplementedError("acc:mediate-worker-decisions:L008-SMOKE-001")
