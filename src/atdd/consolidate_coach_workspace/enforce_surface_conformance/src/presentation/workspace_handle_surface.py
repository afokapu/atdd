"""Public presentation surface for the workspace-handle sanitizer (#1025, E005).

Flat consumers (``coach.utils.multiplexer``) depend on THIS in-feature surface
rather than reaching into the domain module directly, so the domain sanitizer is
consumed within its own feature's layers (SPEC-CODER-COMP-0003) and the flat
multiplexer depends only on the feature's public presentation surface
(strangler-fig). It is a presentation entry point — it imports nothing but the
pure domain function, so a flat top-level import of it carries no
composition/integration weight and cannot form an import cycle.
"""
from __future__ import annotations

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.workspace_handle import (
    sanitize_workspace_handle,
)


def sanitize_cmux_workspace_handle(line: str) -> str:
    """Feature surface over the domain sanitizer — extract the bare ``workspace:N``
    token from a decorated ``cmux list-workspaces`` line."""
    return sanitize_workspace_handle(line)


__all__ = ["sanitize_cmux_workspace_handle"]
