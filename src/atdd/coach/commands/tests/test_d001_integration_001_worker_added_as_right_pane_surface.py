# URN: test:consolidate-coach-workspace:canonical-coach-surface:D001-INTEGRATION-001-worker-added-as-right-pane-surface
# Acceptance: acc:consolidate-coach-workspace:D001-INTEGRATION-001-worker-added-as-right-pane-surface
# WMBT: wmbt:consolidate-coach-workspace:D001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""D001-INTEGRATION-001 — adding a worker creates a surface in the right pane
and zero new panes, leaving the coach pane geometry unchanged.

RED: ``--multiplexer-mode pane`` adds each worker as a new tiled pane, which
re-tiles and shrinks every other pane. This test pins ``add_worker_surface`` —
a worker is placed as a surface/tab in the right pane, never as a new pane.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


_SURFACE_OPS = ("new_surface", "new_surface_in_pane")
_PANE_OPS = ("split_pane", "split", "new_pane", "resize", "new_workspace")


class FakeMx:
    """Multiplexer double — separates surface/tab creation from pane creation
    and pane-geometry mutation."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._n = 0

    def _record(self, op: str, name: Any = None) -> str:
        self._n += 1
        ref = f"ref:{self._n}"
        self.calls.append({"op": op, "ref": ref, "name": name})
        return ref

    def new_surface(self, workspace_ref: Any = None, pane_ref: Any = None,
                    cwd: Any = None, command: Any = None, name: Any = None,
                    direction: Any = None) -> str:
        return self._record("new_surface", name)

    def new_surface_in_pane(self, pane_ref: Any = None, cwd: Any = None,
                            command: Any = None, name: Any = None) -> str:
        return self._record("new_surface_in_pane", name)

    def split_pane(self, ref: Any = None, direction: Any = None, **_: Any) -> str:
        return self._record("split_pane")

    def new_pane(self, *a: Any, **k: Any) -> str:
        return self._record("new_pane")

    def new_workspace(self, cwd: Any = None, command: Any = None,
                      name: Optional[str] = None) -> str:
        return self._record("new_workspace", name)

    def resize(self, ref: Any = None, **_: Any) -> None:
        self._record("resize")

    def surface_count(self) -> int:
        return sum(1 for c in self.calls if c["op"] in _SURFACE_OPS)

    def pane_op_count(self) -> int:
        return sum(1 for c in self.calls if c["op"] in _PANE_OPS)


def test_worker_added_as_right_pane_surface():
    """A second worker is placed as exactly one right-pane surface — no new
    pane, no re-tiling of the coach pane."""
    from atdd.coach.commands import coach

    add_worker = getattr(coach, "add_worker_surface", None)
    assert add_worker is not None, (
        "coach.add_worker_surface is not implemented — workers are still added "
        "as tiled panes that shrink the coach half (RED)"
    )

    mx = FakeMx()
    config = {"repo": {"short_name": "ATDD"}}

    add_worker(mx, "ATDD601", config=config)

    assert mx.surface_count() == 1, (
        f"expected exactly one new right-pane surface; got {mx.surface_count()}"
    )
    assert mx.pane_op_count() == 0, (
        f"adding a worker created/resized {mx.pane_op_count()} pane(s) "
        f"({[c['op'] for c in mx.calls if c['op'] in _PANE_OPS]}); a worker "
        f"must be a surface, so the coach pane geometry stays unchanged"
    )
