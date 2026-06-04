"""resolve_surfacing_values — the single decision point (WMBT E008/L004).

Given an agent kind, resolve the DecisionSurfacingPolicy and render it to the
DispatchSpec values the spawn adapter loads. If a HookPresenceProbe is injected
and reports the wrapper hook path inactive, emit a loud warning — a worker whose
decisions cannot reach the Feed must never be spawned silently.
"""
from __future__ import annotations

import logging
from typing import Optional

from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.ports import (
    HookPresenceProbe,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.decision_surfacing_policy import (
    make_policy,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.surfacing_renderer import (
    SurfacingValues,
    to_dispatch_values,
)

_log = logging.getLogger(__name__)


def resolve(
    agent_kind: str, *, probe: Optional[HookPresenceProbe] = None
) -> SurfacingValues:
    """Resolve the surfacing values for ``agent_kind``.

    Builds the default policy and renders it to the DispatchSpec values. When a
    HookPresenceProbe is injected and reports the wrapper hook path inactive, emit a
    loud warning naming the missing precondition — a worker whose decisions cannot
    reach the Feed must never be spawned silently — then still return the values.
    """
    values = to_dispatch_values(make_policy(agent_kind))
    if probe is not None:
        presence = probe.evaluate()
        if not presence.active:
            _log.warning(
                "cmux Feed-publishing hook path inactive for %s; "
                "worker decisions would not reach the Feed (reason: %s)",
                agent_kind,
                presence.reason,
                extra={"agent_kind": agent_kind, "hook_inactive_reason": presence.reason},
            )
    return values
