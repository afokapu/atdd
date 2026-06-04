"""surfacing_values_provider — the seam the spawn adapter calls (presentation).

The cmux-surface spawn adapter calls ``provide(agent_kind)`` to obtain a worker's
``(permission_mode, allowed_tools)`` before loading them into the DispatchSpec.
The cli-return agent_control path (#969) then reads those values from the spec —
it does not call this provider (it cannot import the wagon, per §3.3).
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.resolve_surfacing_values import (
    resolve,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.src.domain.surfacing_renderer import (
    SurfacingValues,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.src.integration.cmux_hook_probe import (
    CmuxHookProbe,
)


def provide(agent_kind: str) -> SurfacingValues:
    """Return the DispatchSpec surfacing values for ``agent_kind``.

    Delegates to ``resolve`` with a live ``CmuxHookProbe`` so a launch whose
    Feed-publishing hook path is inactive is warned about, not silently spawned.
    """
    return resolve(agent_kind, probe=CmuxHookProbe())
