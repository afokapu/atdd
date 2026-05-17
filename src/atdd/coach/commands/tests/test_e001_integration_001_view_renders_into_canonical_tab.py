# URN: test:consolidate-coach-workspace:canonical-coach-surface:E001-INTEGRATION-001-view-renders-into-canonical-tab
# Acceptance: acc:consolidate-coach-workspace:E001-INTEGRATION-001-view-renders-into-canonical-tab
# WMBT: wmbt:consolidate-coach-workspace:E001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E001-INTEGRATION-001 — the consolidated view renders into the canonical
coach surface and creates no new tab.

RED: there is no ``render_consolidated_view``; nothing renders a multi-issue
status view into a singular surface. This test pins that the render targets the
canonical coach surface and spawns zero new surfaces.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


class FakeMx:
    """Multiplexer double — records surface creations and render (send) targets."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.surfaces: dict[str, str] = {}
        self._n = 0

    def _create(self, name: Any) -> str:
        self._n += 1
        ref = f"surface:{self._n}"
        self.surfaces[ref] = name
        self.calls.append({"op": "create", "ref": ref, "name": name})
        return ref

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        return self._create(name)

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        return self._create(name)

    def list_panes(self) -> list[dict]:
        return [{"ref": r, "name": n} for r, n in self.surfaces.items()]

    def list_workspaces(self) -> list[str]:
        return list(self.surfaces.values())

    def send(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def paste_text(self, ref: str, text: str) -> None:
        self.calls.append({"op": "send", "ref": ref, "text": text})

    def creation_count(self) -> int:
        return sum(1 for c in self.calls if c["op"] == "create")


_RECORDS = [
    {"issue": 736, "phase": "PLANNED", "last_decision": "spawned-planner", "worker_health": "healthy"},
    {"issue": 601, "phase": "RED",     "last_decision": "tests-written",   "worker_health": "healthy"},
]


def test_view_renders_into_canonical_tab():
    """The consolidated view is sent into the canonical coach surface and no
    new surface is created to host it."""
    from atdd.coach.commands import coach

    render = getattr(coach, "render_consolidated_view", None)
    assert render is not None, (
        "coach.render_consolidated_view is not implemented — the consolidated "
        "view has no render path into the canonical surface (RED)"
    )

    mx = FakeMx()
    config = {"repo": {"short_name": "ATDD"}}

    # The canonical coach surface already exists.
    canonical_ref = mx.new_workspace(name="ATDD-coach")
    creations_before = mx.creation_count()

    render(mx, config, _RECORDS)

    assert mx.creation_count() == creations_before, (
        f"render created {mx.creation_count() - creations_before} new "
        f"surface(s); the consolidated view must render into the existing "
        f"canonical surface"
    )
    sends = [c for c in mx.calls if c["op"] == "send"]
    assert sends, "the consolidated view was not rendered into any surface"
    assert all(c["ref"] == canonical_ref for c in sends), (
        f"the consolidated view rendered into a non-canonical surface; "
        f"render targets: {[c['ref'] for c in sends]}, canonical: {canonical_ref!r}"
    )
