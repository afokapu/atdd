"""``FakeAgent`` — in-memory stand-in for the agent-control layer.

The real worker spawns a persona cmux-native, does the phase's work, and calls
``atdd agent done``. The parity test only needs the *signal*: a per-issue queue
of "the current phase's work is finished" markers. ``LocalDryRunRunner`` consumes
one marker per phase advance, so the test drives the lifecycle deterministically
without any subprocess. The real ``CmuxAgentController`` lives in
``atdd.runtime.agent_control``.
"""
from __future__ import annotations


class FakeAgent:
    def __init__(self) -> None:
        self._pending: dict[int, int] = {}

    def signal_phase_done(self, issue_number: int) -> None:
        """Worker signals the current phase's work is complete."""
        self._pending[issue_number] = self._pending.get(issue_number, 0) + 1

    def consume_done(self, issue_number: int) -> bool:
        """Consume one pending done signal. Returns False if none is pending."""
        count = self._pending.get(issue_number, 0)
        if count <= 0:
            return False
        self._pending[issue_number] = count - 1
        return True

    def pending(self, issue_number: int) -> int:
        return self._pending.get(issue_number, 0)
