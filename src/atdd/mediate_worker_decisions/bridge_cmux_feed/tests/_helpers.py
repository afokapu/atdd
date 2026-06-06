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


class FakeWorkerAdvance:
    """Scripts confirm_advanced/nudge for the verify→fallback→escalate path (E009).

    ``results`` is the boolean returned by successive ``confirm_advanced`` calls
    (the first is the post-reply check, the second the post-nudge re-verify). Any
    calls beyond the scripted results default to False (still stuck).
    """

    def __init__(self, results):
        self._results = list(results)
        self.confirm_calls = 0
        self.nudge_calls = []  # list[request_id]

    def confirm_advanced(self, item):
        self.confirm_calls += 1
        return self._results.pop(0) if self._results else False

    def nudge(self, item):
        self.nudge_calls.append(item.request_id)


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
