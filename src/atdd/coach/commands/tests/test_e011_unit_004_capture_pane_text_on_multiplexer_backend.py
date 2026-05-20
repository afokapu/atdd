# URN: test:spawn-agents:coach-spawn-step-by-step-verify-each-stage:E011-UNIT-004-capture-pane-text-on-multiplexer-backend
# Acceptance: acc:spawn-agents:E011-UNIT-004-capture-pane-text-on-multiplexer-backend
# WMBT: wmbt:spawn-agents:E011
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: structural
"""E011-UNIT-004 — MultiplexerBackend exposes capture_pane_text and FakeMultiplexer
implements it, returning a scriptable response.

RED: MultiplexerBackend.capture_pane_text does not exist yet (issue #799).
The current base class has no capture-pane primitive — _assert_worker_processing
checks for capture_surface_text (a different name) and silently skips when absent.
"""
from __future__ import annotations

import inspect


def test_multiplexer_backend_has_capture_pane_text():
    """MultiplexerBackend declares capture_pane_text as a method."""
    from atdd.coach.utils.multiplexer import MultiplexerBackend

    assert hasattr(MultiplexerBackend, "capture_pane_text"), (
        "MultiplexerBackend must define capture_pane_text(surface_ref) -> str"
    )
    method = getattr(MultiplexerBackend, "capture_pane_text")
    assert callable(method)


def test_fake_multiplexer_implements_capture_pane_text():
    """FakeMultiplexer.capture_pane_text returns a string (not raises)."""
    from atdd.coach.utils.multiplexer import FakeMultiplexer

    mux = FakeMultiplexer()
    result = mux.capture_pane_text("surface:1")
    assert isinstance(result, str)


def test_fake_multiplexer_capture_pane_text_scriptable():
    """FakeMultiplexer.capture_pane_text can return scripted responses via _pane_captures."""
    from atdd.coach.utils.multiplexer import FakeMultiplexer

    mux = FakeMultiplexer()
    mux._pane_captures = ["⏺ Thinking..."]  # script first response
    result = mux.capture_pane_text("surface:1")
    assert result == "⏺ Thinking..."
