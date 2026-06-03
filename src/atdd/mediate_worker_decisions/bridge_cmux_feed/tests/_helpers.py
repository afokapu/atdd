"""Shared test doubles for bridge-cmux-feed.

These only import value objects that already exist in the wagon (Verdict). The
feed-specific modules under test are intentionally absent during RED, so this
helper never imports them — keeping unit-test collection unaffected.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY, SOURCE_COACH, Verdict,
)


class FakeFeedTransport:
    """Records ``feed.*.reply`` calls instead of shelling out to cmux."""

    def __init__(self):
        self.calls = []  # list[tuple[verb, params]]

    def reply(self, verb, params):
        self.calls.append((verb, params))


class FakeFeedSource:
    """Returns a fixed set of pending feed items."""

    def __init__(self, items):
        self._items = list(items)

    def list_pending(self):
        return list(self._items)


class FakeCoach:
    """A coach that would auto-approve.

    For a dangerous item the runner must classify human_required BEFORE the
    coach is consulted, so ``calls`` must stay empty in that path (WMBT C003).
    """

    def __init__(self):
        self.calls = []

    def mediate(self, request):
        self.calls.append(request)
        return Verdict(
            verdict_id="v-auto",
            request_id=request.request_id,
            decided_at="t",
            disposition=AUTO_APPLY,
            source=SOURCE_COACH,
            selected_option_id="Alpha",
            reason="auto",
        )
