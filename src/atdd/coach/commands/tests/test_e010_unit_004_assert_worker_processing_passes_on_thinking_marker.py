# URN: test:spawn-agents:worker-launch-prompt-readiness-gate:E010-UNIT-004-assert-worker-processing-passes-on-thinking-marker
# Acceptance: acc:spawn-agents:E010-UNIT-004-assert-worker-processing-passes-on-thinking-marker
# WMBT: wmbt:spawn-agents:E010
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E010-UNIT-004 — _assert_worker_processing returns without raising when
capture-pane contains a thinking indicator or non-empty conversation content.

RED: _assert_worker_processing does not exist in spawn.py yet. The current
code has no post-paste assertion — it fires paste + Enter and immediately
calls capture_session_uuid, logging a phantom transition regardless of
whether the worker processed anything (issue #795).
"""
from __future__ import annotations

import pytest


class _CycleMux:
    """Returns different capture text on successive calls."""

    def __init__(self, responses):
        self._resp = iter(responses)

    def capture_surface_text(self, surface_ref: str) -> str:
        try:
            return next(self._resp)
        except StopIteration:
            return ""


def test_returns_when_thinking_marker_appears(monkeypatch):
    from atdd.coach.commands.spawn import _assert_worker_processing

    mux = _CycleMux([
        "Press up to edit queued messages",  # first poll — not ready
        "⏺ Thinking...",                     # second poll — thinking started
    ])

    _assert_worker_processing(
        surface_ref="surface:6",
        multiplexer=mux,
        timeout_s=2.0,
        poll_interval_s=0.01,
    )


def test_returns_when_non_empty_conversation_appears():
    from atdd.coach.commands.spawn import _assert_worker_processing

    mux = _CycleMux([
        "",                                  # first poll — blank
        "I'll start by reading the issue.",  # non-empty conversation content
    ])

    _assert_worker_processing(
        surface_ref="surface:3",
        multiplexer=mux,
        timeout_s=2.0,
        poll_interval_s=0.01,
    )


def test_at_most_two_capture_calls_before_return():
    from atdd.coach.commands.spawn import _assert_worker_processing

    calls: list[str] = []

    class _TrackingMux:
        def capture_surface_text(self, surface_ref: str) -> str:
            calls.append(surface_ref)
            if len(calls) == 1:
                return "Press up to edit queued messages"
            return "⏺ Thinking..."

    _assert_worker_processing(
        surface_ref="surface:42",
        multiplexer=_TrackingMux(),
        timeout_s=2.0,
        poll_interval_s=0.01,
    )

    assert len(calls) <= 2
