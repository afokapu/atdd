"""Composition root for the coach runtime.

``build_coach_runtime`` wires the use case from explicit collaborators (the test
+ production seam). ``build_coach_runtime_from_repo`` is the production wiring:
real os-backed liveness/signaller, a subprocess spawner over the feed_daemon CLI,
and a file-backed manager registry rooted under ``.atdd/runtime/coach-runtime``.

Skeleton: bodies land in GREEN.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from atdd.mediate_worker_decisions.coach_runtime.src.application.coach_runtime import (
    CoachRuntime,
)


def default_runtime_root(repo_root: Optional[Path] = None) -> Path:
    base = Path(repo_root) if repo_root is not None else Path.cwd()
    return base / ".atdd" / "runtime" / "coach-runtime"


def build_coach_runtime_from_repo(
    *, runtime_root: Optional[Path] = None
) -> CoachRuntime:  # pragma: no cover - live wiring
    raise NotImplementedError("GREEN")


__all__ = ["build_coach_runtime_from_repo", "default_runtime_root"]
