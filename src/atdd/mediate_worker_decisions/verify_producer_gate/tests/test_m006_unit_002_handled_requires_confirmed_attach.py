# URN: test:mediate-worker-decisions:verify-producer-gate:M006-UNIT-002-handled-requires-confirmed-attach
# Acceptance: acc:mediate-worker-decisions:M006-UNIT-002-handled-requires-confirmed-attach
# WMBT: wmbt:mediate-worker-decisions:M006
# Phase: RED
# Layer: application
# Assertion: behavioral
"""M006-UNIT-002 — HANDLED is derived from a confirmed daemon attach.

A published gated decision is recorded HANDLED only when the attach probe confirms a
live daemon scoped to the worker's workspace — attributed to that daemon. Mediation
status is derived from the probe result, never assumed from the mere presence of a
published Feed item: the SAME decision flips HANDLED purely on the probe's answer.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.verify_producer_gate.src.application.verify_producer_gate import (
    evaluate_mediation,
)
from atdd.mediate_worker_decisions.verify_producer_gate.src.domain.mediation_status import (
    CAUSE_MEDIATED,
)
from atdd.mediate_worker_decisions.verify_producer_gate.tests._helpers import (
    StubAttachProbe,
)


def test_handled_only_with_confirmed_attach_attributed_to_daemon():
    decision = {"request_id": "req-2", "workspace_id": "ws-mediated", "tool_name": "Bash"}
    probe = StubAttachProbe(attached=True, daemon_ref="daemon-ws-mediated")

    status = evaluate_mediation(decision, probe)

    # A confirmed attach makes the decision HANDLED, attributed to that daemon.
    assert status.handled is True
    assert status.cause == CAUSE_MEDIATED
    assert status.daemon_ref == "daemon-ws-mediated"
    # The probe was consulted for this worker's workspace — status is not inferred
    # from feed-item presence alone.
    assert probe.calls == ["ws-mediated"]


def test_same_published_decision_flips_handled_on_the_probe_answer():
    decision = {"request_id": "req-3", "workspace_id": "ws-x", "tool_name": "Bash"}

    handled = evaluate_mediation(decision, StubAttachProbe(attached=True, daemon_ref="d"))
    unhandled = evaluate_mediation(decision, StubAttachProbe(attached=False))

    # Identical published decision; HANDLED is decided purely by the attach probe.
    assert handled.handled is True
    assert unhandled.handled is False
