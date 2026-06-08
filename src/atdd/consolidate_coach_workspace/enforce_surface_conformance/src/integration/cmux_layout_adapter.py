"""cmux adapter implementing the layout ports over the existing CmuxBackend.

Maps ``MultiplexerLayoutPort`` onto the real cmux primitives (``new-pane
--direction right``, ``move-surface``) and ``SurfaceScopeProbe`` onto
``surface.list``. cmux-first; tmux/zellij parity is deferred to #601.

RED stub raises NotImplementedError; GREEN fills it in.
"""
from __future__ import annotations

from typing import Any


class CmuxLayoutAdapter:
    """Concrete layout + scope-probe adapter backed by a multiplexer backend."""

    def __init__(self, backend: Any) -> None:
        self._backend = backend

    def create_right_pane(self, from_pane: str, *, workspace_id: str) -> str:
        raise NotImplementedError(
            "enforce-surface-conformance: CmuxLayoutAdapter.create_right_pane (GREEN)"
        )

    def place_surface_right(
        self, surface_ref: str, *, workspace_id: str, pane_ref: str
    ) -> None:
        raise NotImplementedError(
            "enforce-surface-conformance: CmuxLayoutAdapter.place_surface_right (GREEN)"
        )

    def list_identities(self, workspace_id: str) -> list[str]:
        raise NotImplementedError(
            "enforce-surface-conformance: CmuxLayoutAdapter.list_identities (GREEN)"
        )


__all__ = ["CmuxLayoutAdapter"]
