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
    MediationStatus,
)

_log = logging.getLogger(__name__)


def evaluate_mediation(
    decision: Mapping[str, Any], probe: DaemonAttachProbe
) -> MediationStatus:
    """Decide whether ``decision`` was actually mediated.

    ``decision`` is a published gated-decision record carrying at least a
    ``workspace_id``. The HANDLED verdict is gated on ``probe`` confirming a live
    attached daemon for that workspace. GREEN implements the gate.
    """
    raise NotImplementedError(
        "RED #1076 (M006): GREEN gates HANDLED on a confirmed daemon attach and "
        "loud-logs an attach failure instead of recording HANDLED"
    )
