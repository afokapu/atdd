"""Composition root for the coach runtime.

``build_coach_runtime`` wires the use case from explicit collaborators (the test
+ production seam). ``build_coach_runtime_from_repo`` is the production wiring:
real os-backed liveness/signaller, a subprocess spawner over the feed_daemon CLI,
and a file-backed manager registry rooted under ``.atdd/runtime/coach-runtime``.
``resolve_workspace_paths`` derives the per-workspace ledger/lock/cursor paths so
`start` and `wait` agree on where the daemon writes.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Optional

from atdd.mediate_worker_decisions.coach_runtime.src.log import log as _log

from atdd.mediate_worker_decisions.coach_runtime.src.application.coach_runtime import (
    CoachRuntime,
)
from atdd.mediate_worker_decisions.coach_runtime.src.integration.daemon_manager import (
    ManagerRegistry,
    OsLivenessProbe,
    OsSignaller,
    SubprocessDaemonSpawner,
    build_feed_daemon_argv,
    workspace_slug,
)


def default_runtime_root(repo_root: Optional[Path] = None) -> Path:
    base = Path(repo_root) if repo_root is not None else Path.cwd()
    return base / ".atdd" / "runtime" / "coach-runtime"


def resolve_workspace_paths(
    workspace_id: str, *, repo_root: Optional[Path] = None
) -> dict:
    """The per-workspace ledger/lock/cursor paths the daemon + wait share."""
    ws_dir = default_runtime_root(repo_root) / workspace_slug(workspace_id)
    return {
        "lock_path": str(ws_dir / "feed-daemon.lock"),
        "escalations_path": str(ws_dir / "escalations.jsonl"),
        "verdicts_path": str(ws_dir / "verdicts.jsonl"),
        "cursor_path": str(ws_dir / "wait.cursor"),
    }


class _SubprocessGate:
    """Run `atdd gate` as a preflight; never blocks start on a non-zero gate."""

    def run(self) -> int:  # pragma: no cover - real subprocess
        try:
            proc = subprocess.run(["atdd", "gate"], check=False)
            return proc.returncode
        except FileNotFoundError:
            _log.warning(
                "atdd CLI not found on PATH; skipping gate preflight",
                extra={"command": "atdd gate"},
            )
            return 127


def build_coach_runtime(
    *,
    registry,
    spawner,
    liveness,
    signaller,
    gate=None,
    python: Optional[str] = None,
) -> CoachRuntime:
    """Wire the runtime from explicit collaborators (test + production seam)."""
    py = python or sys.executable

    def _argv(*, workspace_id, lock_path, escalations_path, verdicts_path):
        return build_feed_daemon_argv(
            python=py,
            workspace_id=workspace_id,
            lock_path=lock_path,
            escalations_path=escalations_path,
            verdicts_path=verdicts_path,
        )

    return CoachRuntime(
        registry=registry,
        spawner=spawner,
        liveness=liveness,
        signaller=signaller,
        gate=gate,
        daemon_argv=_argv,
    )


def build_coach_runtime_from_repo(
    *, runtime_root: Optional[Path] = None
) -> CoachRuntime:
    """Production wiring: os-backed process control + file-backed registry."""
    root = runtime_root if runtime_root is not None else default_runtime_root()
    return build_coach_runtime(
        registry=ManagerRegistry(root),
        spawner=SubprocessDaemonSpawner(),
        liveness=OsLivenessProbe(),
        signaller=OsSignaller(),
        gate=_SubprocessGate(),
    )


__all__ = [
    "build_coach_runtime",
    "build_coach_runtime_from_repo",
    "default_runtime_root",
    "resolve_workspace_paths",
]
