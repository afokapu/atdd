"""Application ports for enforce-surface-conformance (Protocols only).

The layout pass invokes a REAL multiplexer layout primitive through
``MultiplexerLayoutPort`` — a print of the layout label can never substitute for
an invocation (the #865 log-theater bug). The primitive is a workspace-ordering
op (cmux ``reorder-workspace --after``): it positions a worker's OWN workspace
right of an anchor, never migrating a surface between workspaces, so the
never-collapse invariant is preserved by construction. ``SurfaceScopeProbe`` reads
per-workspace surface identities so the never-collapse post-condition can be
asserted against live state. ``ConformanceLogger`` carries operator-facing intent,
but emitting a log line is observably distinct from invoking the layout port.
"""
from __future__ import annotations

from typing import Protocol


class MultiplexerLayoutPort(Protocol):
    """The real backend layout primitive (cmux-first; #601 for tmux/zellij)."""

    def position_workspace_right(
        self, workspace_id: str, *, anchor_workspace_id: str
    ) -> None:
        """Position ``workspace_id`` immediately right of ``anchor_workspace_id``
        in the operator's window. Geometry over per-workspace surfaces — the
        worker stays its own workspace (and its own daemon scope)."""
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
