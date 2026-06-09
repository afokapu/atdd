"""cmux adapter implementing the layout ports over a multiplexer backend.

``position_workspace_right`` maps to the real cmux ``reorder-workspace --after``
primitive (a workspace-ordering op that keeps each worker its own workspace, so
never-collapse holds by construction). ``list_identities`` maps to the cmux
``surface.list`` probe. cmux-first; tmux/zellij parity is deferred to #601.
"""
from __future__ import annotations

from typing import Any


class CmuxLayoutAdapter:
    """Concrete layout + scope-probe adapter backed by a multiplexer backend.

    Implements both ``MultiplexerLayoutPort`` and ``SurfaceScopeProbe`` so a single
    object can be wired for both ports at the composition root.
    """

    def __init__(self, backend: Any) -> None:
        self._backend = backend

    # MultiplexerLayoutPort
    def position_workspace_right(
        self, workspace_id: str, *, anchor_workspace_id: str
    ) -> None:
        self._backend.reorder_workspace_after(workspace_id, anchor_workspace_id)

    # SurfaceScopeProbe
    def list_identities(self, workspace_id: str) -> list[str]:
        return list(self._backend.list_surface_identities(workspace_id))


__all__ = ["CmuxLayoutAdapter"]
