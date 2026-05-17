# URN: test:consolidate-coach-workspace:canonical-coach-surface:Y001-INTEGRATION-001-two-issues-resolve-to-one-tab
# Acceptance: acc:consolidate-coach-workspace:Y001-INTEGRATION-001-two-issues-resolve-to-one-tab
# WMBT: wmbt:consolidate-coach-workspace:Y001
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""Y001-INTEGRATION-001 — driving two managed issues resolves to exactly one
coach orchestration surface; the second resolution attaches to the surface the
first created.

RED: there is no resolve-or-create path for a singular coach surface, so each
coach invocation opens its own ``ATDD-coach-<N>`` tab. This test pins
``coach.resolve_or_create_coach_surface`` — the second call must find and
return the existing canonical surface rather than creating a second one.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

pytestmark = [pytest.mark.platform]


class FakeMx:
    """Multiplexer double — records every surface/tab creation."""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.surfaces: dict[str, str] = {}  # ref -> name
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

    def creation_count(self) -> int:
        return sum(1 for c in self.calls if c["op"] == "create")


def test_two_issues_resolve_to_one_tab():
    """Resolving the coach surface for #736 then #601 yields a single surface."""
    from atdd.coach.commands import coach

    resolve = getattr(coach, "resolve_or_create_coach_surface", None)
    assert resolve is not None, (
        "coach.resolve_or_create_coach_surface is not implemented — there is "
        "no resolve-or-create path for a singular coach orchestration tab (RED)"
    )

    mx = FakeMx()
    config = {"repo": {"short_name": "ATDD"}}

    ref_736 = resolve(mx, config, 736)
    ref_601 = resolve(mx, config, 601)

    assert mx.creation_count() == 1, (
        f"expected exactly one orchestration surface across both resolutions; "
        f"{mx.creation_count()} were created — the second invocation opened a "
        f"new tab instead of attaching to the existing one"
    )
    assert ref_736 == ref_601, (
        f"the second resolution returned a new surface ({ref_601!r}) instead "
        f"of the already-created canonical surface ({ref_736!r})"
    )
    assert mx.surfaces[ref_736] == "ATDD-coach", (
        f"the orchestration surface is named {mx.surfaces[ref_736]!r}; "
        f"expected the canonical coach tab name 'ATDD-coach'"
    )
