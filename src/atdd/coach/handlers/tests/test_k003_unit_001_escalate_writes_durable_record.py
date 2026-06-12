# URN: test:mediate-worker-decisions:feed-daemon-durability:K003-UNIT-001-escalate-writes-durable-record
# Acceptance: acc:mediate-worker-decisions:K003-UNIT-001-escalate-writes-durable-record
# WMBT: wmbt:mediate-worker-decisions:K003
# Phase: RED
# Layer: application
# Assertion: behavioral
"""K003-UNIT-001 — coach-side _escalate leaves a durable record, not just stderr.

``_escalate`` only prints to stderr (and only when ``escalation_channel`` is
set), while the durable ``escalations.jsonl`` is written by the daemon alone — so
a coach-raised escalation vanishes the moment stderr scrolls away. ``_escalate``
must additionally append a durable escalation record (mirroring the coach
``decisions.jsonl`` sink at ``<runtime_dir>/coach/escalations.jsonl``) carrying
the reason.

RED: today ``_escalate`` writes no file. Fails until the durable write lands.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.handlers.state_machine import CoachContext

pytestmark = [pytest.mark.platform]


def test_escalate_appends_a_durable_record(tmp_path, monkeypatch):
    from atdd.coach.handlers import spawn as spawn_handler

    runtime_root = tmp_path / ".atdd" / "runtime"
    ctx = CoachContext(
        issue_number=1084,
        runtime_dir=runtime_root,
        escalation_channel="file:./escalations.log",
    )

    reason = "spawn failed after 3 attempts for #1084 (tester/RED)"
    spawn_handler._escalate(ctx, reason)

    ledger = runtime_root / "coach" / "escalations.jsonl"
    assert ledger.is_file(), (
        "_escalate left no durable escalations.jsonl — a coach-side escalation "
        "has no audit sink and is lost when stderr scrolls (K003/A0)"
    )

    lines = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1, f"expected exactly one durable escalation, got {lines}"
    assert reason in ledger.read_text(encoding="utf-8"), (
        "the durable escalation record does not carry the escalation reason"
    )
