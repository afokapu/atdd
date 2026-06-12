"""Kill-old-agent-before-respawn primitive (#1079, WMBT E031).

On a phase transition the coach must terminate the issue's currently-bound
worker and CONFIRM it is dead BEFORE relaunching the next persona — otherwise a
ghost agent survives the transition and gets relabeled as the new persona
(observed live driving #1055/#1057/#1062/#1066). The kill is CLI-agnostic (via
the ``AgentController`` abstraction, never a hardcoded ``/exit``) and scoped to
the prior worker's handle. If the kill cannot be confirmed, the respawn refuses
rather than stacking a second live agent on the issue.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from atdd.runtime.agent_control import AgentHandle, AgentSignal, DispatchSpec


@runtime_checkable
class WorkerLifecycleController(Protocol):
    """The integration port the respawn use-case drives (a kill-and-confirm-capable
    ``AgentController``).

    This is the explicit seam SMOKE flagged: ``respawn_worker`` needs a controller
    that can confirm liveness (``is_alive``) on top of the base
    ``atdd.runtime.agent_control.AgentController`` surface. The real controllers do
    not expose ``is_alive`` yet — wiring that in is what turns the deferred
    E031-SMOKE into a live one (docs/smoke-audit.md, #1079).
    """

    def signal(self, handle: AgentHandle, sig: AgentSignal) -> None: ...

    def stop(self, handle: AgentHandle, *, reason: str) -> None: ...

    def is_alive(self, handle: AgentHandle) -> bool: ...

    def spawn(self, spec: DispatchSpec) -> AgentHandle: ...


@dataclass(frozen=True)
class RespawnOutcome:
    """Result of a kill-before-respawn attempt (the orchestrator branches on it)."""

    reaped: bool
    relaunched: bool
    refused: bool
    new_handle: Optional[AgentHandle]
    reason: str


def respawn_worker(
    controller: WorkerLifecycleController,
    old_handle: AgentHandle,
    new_spec: DispatchSpec,
    *,
    confirm_retries: int = 3,
) -> RespawnOutcome:
    """Terminate ``old_handle`` and, only once confirmed dead, spawn ``new_spec``.

    The terminate goes through the agent_control abstraction (INTERRUPT then
    ``stop``) — never a CLI-specific quit literal. Liveness is confirmed via
    ``controller.is_alive``; if the worker is still alive after ``confirm_retries``
    probes the respawn refuses (no relaunch), so the issue never carries two live
    agents across the boundary.
    """
    controller.signal(old_handle, AgentSignal.INTERRUPT)
    controller.stop(old_handle, reason="phase-transition respawn: reap prior worker")

    for _ in range(max(confirm_retries, 1)):
        if not controller.is_alive(old_handle):
            break

    if controller.is_alive(old_handle):
        return RespawnOutcome(
            reaped=False,
            relaunched=False,
            refused=True,
            new_handle=None,
            reason=(
                f"refused respawn: could not confirm kill of prior worker "
                f"{old_handle.agent_id} — not launching next persona to avoid a "
                f"second live agent"
            ),
        )

    new_handle = controller.spawn(new_spec)
    return RespawnOutcome(
        reaped=True,
        relaunched=True,
        refused=False,
        new_handle=new_handle,
        reason="",
    )
