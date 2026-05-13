# URN: test:integration-hardening:coach-single-command-driver:L003-UNIT-001-multiplexer-abc-supports-new-surface-in-pane
# Acceptance: acc:integration-hardening:L003-UNIT-001-multiplexer-abc-supports-new-surface-in-pane
# WMBT: wmbt:integration-hardening:L003
# Phase: RED
# Layer: unit
"""L003-UNIT-001 — MultiplexerBackend.new_surface_in_pane exists; FakeMultiplexer records (pane_ref, name).

Verifies the ABC contract (#658): new_surface_in_pane attaches a surface to an
existing pane without creating a new grid slot; FakeMultiplexer records the call
with op='new_surface_in_pane' and pane_ref; surface_to_pane reverses the lookup.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_fake_multiplexer_records_new_surface_in_pane():
    from atdd.coach.utils.multiplexer import FakeMultiplexer

    fake = FakeMultiplexer()
    surface_ref = fake.new_surface_in_pane(
        pane_ref="pane:1",
        cwd="/tmp",
        command="echo hi",
        name="test-tab",
    )

    assert surface_ref.startswith("surface:"), f"Expected surface ref, got {surface_ref!r}"

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["op"] == "new_surface_in_pane"
    assert call["pane_ref"] == "pane:1"
    assert call["name"] == "test-tab"
    assert call["cwd"] == "/tmp"
    assert call["command"] == "echo hi"


def test_fake_multiplexer_surface_to_pane_reverses_lookup():
    from atdd.coach.utils.multiplexer import FakeMultiplexer

    fake = FakeMultiplexer()
    surface_ref = fake.new_surface_in_pane(pane_ref="pane:7", cwd=None, command=None, name="obs")

    assert fake.surface_to_pane(surface_ref) == "pane:7"


def test_fake_multiplexer_new_surface_also_records_pane():
    from atdd.coach.utils.multiplexer import FakeMultiplexer

    fake = FakeMultiplexer()
    surface_ref = fake.new_surface(cwd="/tmp", command="claude", name="persona")

    pane_ref = fake.surface_to_pane(surface_ref)
    assert pane_ref.startswith("pane:"), f"Expected pane ref, got {pane_ref!r}"


def test_multiplexer_abc_raises_not_implemented():
    from atdd.coach.utils.multiplexer import MultiplexerBackend, MultiplexerRef
    from typing import Optional

    class _Minimal(MultiplexerBackend):
        name = "minimal"

        def new_workspace(self, cwd: str, command: str, name: Optional[str] = None) -> MultiplexerRef:
            return "workspace:1"

        def read_screen(self, ref: MultiplexerRef, lines: int = 50) -> str:
            return ""

        def send(self, ref: MultiplexerRef, text: str) -> None:
            pass

        def send_key(self, ref: MultiplexerRef, key: str) -> None:
            pass

        def list_workspaces(self) -> list[str]:
            return []

        def close(self, ref: MultiplexerRef) -> None:
            pass

    backend = _Minimal()
    with pytest.raises(NotImplementedError):
        backend.new_surface_in_pane("pane:1")
    with pytest.raises(NotImplementedError):
        backend.surface_to_pane("surface:1")
