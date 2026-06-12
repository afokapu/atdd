# URN: test:mediate-worker-decisions:feed-daemon-durability:K003-UNIT-002-durable-write-independent-of-stderr-channel
# Acceptance: acc:mediate-worker-decisions:K003-UNIT-002-durable-write-independent-of-stderr-channel
# WMBT: wmbt:mediate-worker-decisions:K003
# Phase: RED
# Layer: application
# Assertion: behavioral
"""K003-UNIT-002 — the durable escalation is written even with no stderr channel.

Today ``_escalate`` is gated entirely on ``escalation_channel`` being set: with
no channel it does nothing at all. The durable audit record must NOT depend on
the legacy stderr channel — a coach-side escalation is always recoverable from
disk.

RED: with ``escalation_channel=None`` today ``_escalate`` is a complete no-op and
writes nothing. Fails until the durable write lands unconditionally.
"""
from __future__ import annotations

import pytest

from atdd.coach.handlers.state_machine import CoachContext

pytestmark = [pytest.mark.platform]


def test_durable_write_independent_of_stderr_channel(tmp_path):
    from atdd.coach.handlers import spawn as spawn_handler

    runtime_root = tmp_path / ".atdd" / "runtime"
    ctx = CoachContext(
        issue_number=1084,
        runtime_dir=runtime_root,
        escalation_channel=None,  # no legacy stderr channel configured
    )

    spawn_handler._escalate(ctx, "persona did not materialise for #1084")

    ledger = runtime_root / "coach" / "escalations.jsonl"
    assert ledger.is_file(), (
        "_escalate wrote no durable record when escalation_channel is unset — "
        "the audit sink must not depend on the stderr channel (K003/A0)"
    )
    lines = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1, f"expected one durable escalation, got {lines}"
