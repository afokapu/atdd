# URN: test:mediate-worker-decisions:surface-worker-decisions:E013-UNIT-002-dispatch-refuses-when-hook-path-inactive
# Acceptance: acc:mediate-worker-decisions:E013-UNIT-002-dispatch-refuses-when-hook-path-inactive
# WMBT: wmbt:mediate-worker-decisions:E013
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E013-UNIT-002 — the dispatch refuses to spawn when the hook path is inactive.

When the Feed-publishing hook path is inactive, the dispatch gate raises
FeedHookInactiveError (naming the missing precondition) rather than letting a
silently non-publishing, unmediated worker be spawned. An active hook path passes.
"""
from __future__ import annotations

import pytest

from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.ports import (
    HookPresence,
)
from atdd.mediate_worker_decisions.surface_worker_decisions.src.presentation.dispatch_feed_hook_gate import (
    FeedHookInactiveError,
    assert_dispatch_feed_hook_active,
)


class _Probe:
    def __init__(self, presence: HookPresence) -> None:
        self._presence = presence

    def evaluate(self) -> HookPresence:
        return self._presence


def test_inactive_hook_path_refuses_loudly():
    probe = _Probe(HookPresence(active=False, reason="CMUX_SURFACE_ID not set"))
    with pytest.raises(FeedHookInactiveError) as exc:
        assert_dispatch_feed_hook_active(probe=probe)
    assert "CMUX_SURFACE_ID" in str(exc.value)  # names the missing precondition


def test_active_hook_path_passes():
    probe = _Probe(HookPresence(active=True, reason=""))
    # No exception: an active hook path is allowed to spawn.
    assert_dispatch_feed_hook_active(probe=probe)
