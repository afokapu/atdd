"""resolve_surfacing_values — the single decision point (WMBT E008/L004).

Given an agent kind, resolve the DecisionSurfacingPolicy and render it to the
DispatchSpec values the spawn adapter loads. If a HookPresenceProbe is injected
and reports the wrapper hook path inactive, emit a loud warning — a worker whose
decisions cannot reach the Feed must never be spawned silently.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import yaml

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


def _session_convention_path() -> Path:
    """Locate ``session.convention.yaml`` from the installed ``atdd`` package.

    Resolved off the package root (not a sibling-wagon import) so this stays a data
    read, not a code coupling: ``<atdd>/coach/conventions/session.convention.yaml``.
    """
    import atdd

    return (
        Path(atdd.__file__).resolve().parent
        / "coach"
        / "conventions"
        / "session.convention.yaml"
    )


def _convention_freedom_set() -> Optional[Tuple[str, ...]]:
    """Read the config-driven freedom set (``allowed_tools ∪ allowed_bash``) from
    ``session.convention.yaml::spawn_time.freedom_layer`` (E031 #1062).

    The convention is the source of truth for the scoped safe allow-list; both launch
    transports realize it via this single resolve() seam. Returns ``None`` if the
    convention does not declare the data (falls back to the pure default set) — a
    missing convention must never silently widen the allow-list.
    """
    try:
        data = yaml.safe_load(_session_convention_path().read_text(encoding="utf-8"))
        freedom_layer = (data or {}).get("spawn_time", {}).get("freedom_layer", {})
        allowed = list(freedom_layer.get("allowed_tools") or [])
        allowed += list(freedom_layer.get("allowed_bash") or [])
    except (OSError, yaml.YAMLError) as exc:
        _log.warning(
            "could not read freedom_layer from session convention; "
            "falling back to default auto-allow set",
            extra={"error": str(exc)},
        )
        return None
    return tuple(allowed) if allowed else None


def resolve(
    agent_kind: str, *, probe: Optional[HookPresenceProbe] = None
) -> SurfacingValues:
    """Resolve the surfacing values for ``agent_kind``.

    Builds the default policy and renders it to the DispatchSpec values. When a
    HookPresenceProbe is injected and reports the wrapper hook path inactive, emit a
    loud warning naming the missing precondition — a worker whose decisions cannot
    reach the Feed must never be spawned silently — then still return the values.
    """
    values = to_dispatch_values(
        make_policy(agent_kind, auto_allow_tools=_convention_freedom_set())
    )
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
