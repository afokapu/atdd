"""verify_producer_gate — the S0 gate decision points (WMBT C010/M006).

STUB (RED #1076): the contract surface only. GREEN implements:

* ``evaluate_mediation`` — given a published gated decision and a
  ``DaemonAttachProbe``, return a ``MediationStatus`` that is HANDLED ONLY when
  the probe confirms a live daemon attached to the worker's workspace; when not
  attached, return UNMEDIATED (cause=no_attached_daemon) and loud-log the missing
  precondition — never a silent HANDLED for an unmediated worker (#1084/A1).
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from atdd.mediate_worker_decisions.verify_producer_gate.src.application.ports import (
    DaemonAttachProbe,
)
from atdd.mediate_worker_decisions.verify_producer_gate.src.domain.mediation_status import (
    CAUSE_MEDIATED,
    CAUSE_NO_ATTACHED_DAEMON,
    MediationStatus,
)

_log = logging.getLogger(__name__)


def evaluate_mediation(
    decision: Mapping[str, Any], probe: DaemonAttachProbe
) -> MediationStatus:
    """Decide whether ``decision`` was actually mediated.

    ``decision`` is a published gated-decision record carrying at least a
    ``workspace_id``. The HANDLED verdict is gated on ``probe`` confirming a live
    attached daemon for that workspace: when no daemon is attached, the decision is
    UNMEDIATED (loud-logged), never a silent HANDLED for an unmediated worker.
    """
    workspace = decision["workspace_id"]
    state = probe.evaluate(workspace)
    if not state.attached:
        _log.warning(
            "no live daemon attached to workspace; published decision is UNMEDIATED, "
            "not HANDLED",
            extra={
                "workspace_id": workspace,
                "request_id": decision.get("request_id"),
                "attach_reason": state.reason,
            },
        )
        return MediationStatus(
            handled=False, cause=CAUSE_NO_ATTACHED_DAEMON, daemon_ref=None
        )
    return MediationStatus(
        handled=True, cause=CAUSE_MEDIATED, daemon_ref=state.daemon_ref
    )
