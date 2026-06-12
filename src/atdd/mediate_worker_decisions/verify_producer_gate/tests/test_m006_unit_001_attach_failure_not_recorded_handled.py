# URN: test:mediate-worker-decisions:verify-producer-gate:M006-UNIT-001-attach-failure-not-recorded-handled
# Acceptance: acc:mediate-worker-decisions:M006-UNIT-001-attach-failure-not-recorded-handled
# WMBT: wmbt:mediate-worker-decisions:M006
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M006-UNIT-001 — a daemon-attach failure is not recorded HANDLED.

A worker's gated decision is published to the Feed, but its workspace has NO live
attached daemon (the probe reports not-attached). The gate must record the decision
as UNMEDIATED (handled is False, cause=no_attached_daemon) and loud-log the missing
mediation precondition — never a silent HANDLED for an unmediated worker (#1084/A1).
"""
from __future__ import annotations

import logging

from atdd.mediate_worker_decisions.verify_producer_gate.src.application import (
    verify_producer_gate as gate,
)
from atdd.mediate_worker_decisions.verify_producer_gate.src.application.verify_producer_gate import (
    evaluate_mediation,
)
from atdd.mediate_worker_decisions.verify_producer_gate.src.domain.mediation_status import (
    CAUSE_NO_ATTACHED_DAEMON,
)
from atdd.mediate_worker_decisions.verify_producer_gate.tests._helpers import (
    StubAttachProbe,
)


def test_attach_failure_flags_unmediated_and_loud_logs(caplog):
    decision = {"request_id": "req-1", "workspace_id": "ws-unmediated", "tool_name": "Bash"}
    probe = StubAttachProbe(attached=False, reason="daemon-attach failed")

    with caplog.at_level(logging.WARNING, logger=gate._log.name):
        status = evaluate_mediation(decision, probe)

    # The published decision is NOT mediated — it must not masquerade as HANDLED.
    assert status.handled is False
    assert status.cause == CAUSE_NO_ATTACHED_DAEMON

    # And the missing-mediation precondition is loud, not silently swallowed.
    loud = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert loud, "a daemon-attach failure must be loud-logged, never silently HANDLED"
