"""surfacing_renderer — render a DecisionSurfacingPolicy to DispatchSpec values (WMBT Y002).

Pure: a policy in, the ``(permission_mode, allowed_tools)`` pair that the spawn
adapter loads onto ``DispatchSpec`` out. The renderer is the exact image of the
policy — every ``auto_allow`` tool is present, every ``surface`` tool (Bash) is
absent — so the two launch transports can never diverge from the declared policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.decision_surfacing_policy import (
    DecisionSurfacingPolicy,
    validate_policy,
)


@dataclass(frozen=True)
class SurfacingValues:
    """The DispatchSpec-bound values produced from a policy.

    ``permission_mode`` and ``allowed_tools`` are field-compatible with
    ``atdd.runtime.agent_control.DispatchSpec`` so the spawn adapter can load them
    directly; this module does not import DispatchSpec (keeps the wagon decoupled).
    """

    permission_mode: str
    allowed_tools: Tuple[str, ...]


def to_dispatch_values(policy: DecisionSurfacingPolicy) -> SurfacingValues:
    """Render ``policy`` to the DispatchSpec ``(permission_mode, allowed_tools)`` values.

    The renderer is the exact image of the policy: allowed_tools is the auto_allow
    set with every surface tool removed (so an action-class tool can never leak in),
    and permission_mode is the policy mode. Validated first so a surfacing-suppressing
    policy raises rather than rendering.
    """
    validate_policy(policy)
    surface = set(policy.surface_tools)
    allowed = tuple(t for t in policy.auto_allow_tools if t not in surface)
    return SurfacingValues(permission_mode=policy.permission_mode, allowed_tools=allowed)
