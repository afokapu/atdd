"""Dispatch -> daemon attach (issue #1025, WMBT E012).

`atdd coach <N>` (the dispatch) spawns a worker but never starts a decision
daemon (coach.py routes only start/wait/next/stop/daemons to coach_runtime), so a
dispatch-spawned worker is unmediated by construction. This thin presentation
seam closes that gap: given the freshly-spawned worker's cmux surface, it
resolves the worker's OWN workspace and reuses ``CoachRuntime.start`` (idempotent)
to attach a workspace-scoped feed_daemon to it. The dispatch spawn handler calls
this once per worker after a successful spawn.

Reuses the daemon-as-surface start path wholesale; adds no new daemon mechanism.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from atdd.mediate_worker_decisions.coach_runtime.src.domain.managed_daemon import (
    ManagedDaemon,
)


def attach_worker_daemon(
    backend: Any,
    worker_surface_ref: str,
    *,
    repo_cwd: Optional[Path] = None,
    runtime: Optional[Any] = None,
) -> Optional[ManagedDaemon]:
    """Resolve the worker's workspace and start a scoped daemon (idempotent).

    ``backend`` resolves ``worker_surface_ref`` to its owning cmux workspace;
    ``runtime`` (default: the repo composition root) starts the workspace-scoped
    feed_daemon. A workspace that already has a live managed daemon is a no-op —
    the existing record is returned. The gate is NOT re-run here (the dispatch
    already gated); ``run_gate=False``.
    """
    from atdd.mediate_worker_decisions.coach_runtime.composition import (
        build_coach_runtime_from_repo,
        resolve_workspace_paths,
    )

    workspace_id = backend.surface_workspace(worker_surface_ref)
    if runtime is None:
        runtime = build_coach_runtime_from_repo(repo_cwd=repo_cwd)
    paths = resolve_workspace_paths(workspace_id, repo_root=repo_cwd)
    return runtime.start(
        workspace_id,
        lock_path=paths["lock_path"],
        escalations_path=paths["escalations_path"],
        verdicts_path=paths["verdicts_path"],
        run_gate=False,
    )


__all__ = ["attach_worker_daemon"]
