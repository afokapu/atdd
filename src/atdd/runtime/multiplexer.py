"""``atdd.runtime.multiplexer`` — view-only multiplexer Protocol (Child 6, §4.9).

The multiplexer is for **observability only**: open a pane and tail an agent's
output.log into it, list/close surfaces, list workspaces. Prompt delivery, ready
detection, and stdin/interrupt forwarding belong to
``atdd.runtime.agent_control`` — NOT here.

**Forbidden methods** (would re-introduce screen-scrape control) MUST NOT exist
on this Protocol surface:

* ``paste_text``      — control path → ``AgentController.deliver_prompt``
* ``send_key``        — control path → ``AgentController.signal``
* ``capture_pane_text`` — control path → ``AgentController.stream_events``

The import-discipline test (tests/architecture/test_layer_imports.py) asserts
none of these exist on this Protocol.

Dependency rule (§3.3): stdlib + subprocess only. MUST NOT import
``atdd.coach.*``, ``atdd.train.*``, ``atdd.integrations.*``, or
``atdd.runtime.agent_control``. ``attach_view`` therefore types its handle
argument structurally (``object``) rather than importing ``AgentHandle`` from
the sibling agent_control layer — only ``handle.output_log`` is read.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SurfaceRef:
    """Opaque reference to an open multiplexer surface (pane/tab)."""

    surface_id: str
    workspace_id: str | None = None


@dataclass(frozen=True)
class WorkspaceRef:
    """Opaque reference to a multiplexer workspace (window/session)."""

    workspace_id: str


@runtime_checkable
class Multiplexer(Protocol):
    """View-only surface lifecycle for observability (§4.9)."""

    def attach_view(self, handle: object) -> SurfaceRef:
        """Open a pane and tail ``handle.output_log`` into it (read-only).

        ``handle`` is an ``atdd.runtime.agent_control.AgentHandle`` (typed
        ``object`` to avoid a cross-layer import, §3.3); only its read-only
        ``output_log`` attribute is consumed.
        """
        ...

    def list_surfaces(self) -> list[SurfaceRef]: ...

    def close_surface(self, ref: SurfaceRef) -> None: ...

    def list_workspaces(self) -> list[WorkspaceRef]: ...
