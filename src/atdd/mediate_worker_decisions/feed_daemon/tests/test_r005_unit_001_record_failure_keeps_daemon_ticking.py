# URN: test:mediate-worker-decisions:feed-daemon-durability:R005-UNIT-001-record-failure-keeps-daemon-ticking
# Acceptance: acc:mediate-worker-decisions:R005-UNIT-001-record-failure-keeps-daemon-ticking
# WMBT: wmbt:mediate-worker-decisions:R005
# Phase: RED
# Layer: application
# Assertion: behavioral
"""R005-UNIT-001 — a verdict-ledger record() failure does not kill the tick.

In ``tick`` the ``verdicts.record`` / ``escalations.record`` calls are unguarded
and the answered-set ``mark()`` runs only after them, so a raising ``record()``
(disk full, permission, IO) unwinds the whole loop: the daemon dies and the
remaining items are never processed. A write failure on ONE item must be
contained so the poll loop proceeds to the next item.

RED: today the first record() exception propagates straight out of ``tick`` —
the second item is never reached. Fails until record() is wrapped.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import FeedItem
from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import make_daemon


def _safe_question(suffix):
    return FeedItem(
        id=f"f-{suffix}",
        request_id=f"req-{suffix}",
        kind="question",
        question_prompt="Pick an option",
        question_options=(
            {"id": "Alpha", "label": "Alpha", "description": ""},
            {"id": "Beta", "label": "Beta", "description": ""},
        ),
        tool_name=None,
        tool_input=None,
    )


class _RaiseOnceVerdictLedger:
    """record() raises on the first call, then succeeds — models a transient IO fault."""

    def __init__(self):
        self.records = []
        self.calls = 0

    def record(self, verdict):
        self.calls += 1
        if self.calls == 1:
            raise OSError("No space left on device")
        self.records.append(verdict)


def test_record_failure_keeps_daemon_ticking():
    ledger = _RaiseOnceVerdictLedger()
    first, second = _safe_question("one"), _safe_question("two")
    daemon, source, transport, coach = make_daemon(
        items=[first, second], verdict_ledger=ledger
    )

    # The tick must NOT propagate the record() exception.
    outcomes = daemon.tick()

    # Both items were processed — the loop was not unwound by the first failure.
    assert ledger.calls == 2, (
        "the second item never reached verdicts.record — the record() failure "
        "on the first item unwound the whole tick (R005)"
    )
    assert daemon._answered.seen(second.request_id), (
        "the second item was never marked answered — the daemon died on item one"
    )
    assert len(outcomes) == 2
