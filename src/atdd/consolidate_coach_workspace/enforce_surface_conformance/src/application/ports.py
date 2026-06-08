"""Application ports for enforce-surface-conformance (Protocols only).

The layout pass invokes a REAL multiplexer layout primitive through
``MultiplexerLayoutPort`` — a print of the layout label can never substitute for
an invocation (the #865 log-theater bug). ``SurfaceScopeProbe`` reads per-workspace
surface identities so the never-collapse post-condition can be asserted against
live state. ``ConformanceLogger`` carries operator-facing intent, but emitting a
log line is observably distinct from invoking the layout port.
"""
from __future__ import annotations

from typing import Protocol


class MultiplexerLayoutPort(Protocol):
    """The real backend layout primitives (cmux-first; #601 for tmux/zellij)."""

    def create_right_pane(self, from_pane: str, *, workspace_id: str) -> str:
        """Create the right-region pane for a worker's own workspace; return its ref."""
        ...

    def place_surface_right(
        self, surface_ref: str, *, workspace_id: str, pane_ref: str
    ) -> None:
        """Place ``surface_ref`` (in its OWN workspace) into the right region —
        geometry only; never migrates the surface into another workspace."""
        ...


class SurfaceScopeProbe(Protocol):
    """Reads the distinct worker identities resident in a workspace."""

    def list_identities(self, workspace_id: str) -> list[str]:
        """Return the worker identities ``surface.list`` reports for the workspace.

        A single-identity workspace yields exactly one identity.
        """
        ...


class ConformanceLogger(Protocol):
    """Structured operator-facing emit — distinct from a layout invocation."""

    def emit(self, message: str, *, rule_id: str) -> None: ...
