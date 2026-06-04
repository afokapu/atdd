# URN: test:mediate-worker-decisions:feed-daemon:E005-INTEGRATION-001-rehydrate-across-restart
# Acceptance: acc:mediate-worker-decisions:E005-INTEGRATION-001-rehydrate-across-restart
# WMBT: wmbt:mediate-worker-decisions:E005
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E005-INTEGRATION-001 — idempotent across a restart via durable re-hydration.

A first daemon answers one safe item (-> verdicts.jsonl) and escalates one
dangerous item (-> escalations.jsonl). A second daemon, built from the same two
ledger paths, re-hydrates its answered-set from those files and re-answers /
re-escalates NOTHING: its coach and transport are never called and no new ledger
lines are written.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.feed_daemon.composition import build_feed_daemon
from atdd.mediate_worker_decisions.feed_daemon.src.domain.answered_set import AnsweredSet
from atdd.mediate_worker_decisions.feed_daemon.src.integration.jsonl_ledgers import (
    JsonlEscalationSink,
    JsonlVerdictLedger,
    read_handled_request_ids,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.composition import build_feed_runner
from atdd.mediate_worker_decisions.feed_daemon.tests._helpers import (
    DANGER_PERMISSION,
    SAFE_QUESTION,
    CountingFeedSource,
    FakeCoach,
    FakeFeedTransport,
    NeverStop,
    RecordingLock,
    FakeSleeper,
)


def _lines(path):
    return path.read_text().splitlines() if path.exists() else []


def test_restart_rehydrates_and_re_answers_nothing(tmp_path):
    verdicts = tmp_path / "verdicts.jsonl"
    escalations = tmp_path / "escalations.jsonl"
    items = [SAFE_QUESTION, DANGER_PERMISSION]

    # --- first daemon run: answers safe, escalates dangerous, writes ledgers ---
    src1 = CountingFeedSource(items)
    runner1 = build_feed_runner(source=src1, reply=FakeFeedTransport(), coach=FakeCoach())
    daemon1 = build_feed_daemon(
        source=src1,
        runner=runner1,
        escalation_sink=JsonlEscalationSink(escalations),
        verdict_ledger=JsonlVerdictLedger(verdicts),
        sleeper=FakeSleeper(),
        stop=NeverStop(),
        lock=RecordingLock(),
        answered=AnsweredSet(),
    )
    daemon1.tick()
    assert len(_lines(verdicts)) == 1
    assert len(_lines(escalations)) == 1

    # --- second daemon: re-hydrate answered-set from the durable ledgers ---
    answered2 = AnsweredSet(read_handled_request_ids(verdicts, escalations))
    src2 = CountingFeedSource(items)
    transport2 = FakeFeedTransport()
    coach2 = FakeCoach()
    runner2 = build_feed_runner(source=src2, reply=transport2, coach=coach2)
    daemon2 = build_feed_daemon(
        source=src2,
        runner=runner2,
        escalation_sink=JsonlEscalationSink(escalations),
        verdict_ledger=JsonlVerdictLedger(verdicts),
        sleeper=FakeSleeper(),
        stop=NeverStop(),
        lock=RecordingLock(),
        answered=answered2,
    )

    daemon2.tick()

    assert coach2.calls == []            # nothing re-answered
    assert transport2.calls == []        # nothing re-replied
    assert len(_lines(verdicts)) == 1    # no new verdict line
    assert len(_lines(escalations)) == 1  # no new escalation line
