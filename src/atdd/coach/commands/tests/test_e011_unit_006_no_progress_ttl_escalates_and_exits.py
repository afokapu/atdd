# URN: test:govern-lifecycle:coach-single-instance-lock-and-zombie-reaping:E011-UNIT-006-no-progress-ttl-escalates-and-exits
# Acceptance: acc:govern-lifecycle:E011-UNIT-006-no-progress-ttl-escalates-and-exits
# WMBT: wmbt:govern-lifecycle:E011
# Phase: GREEN
# Layer: backend.unit
# Assertion: behavioral

"""acc:govern-lifecycle:E011-UNIT-006 — no-progress TTL check escalates and returns True."""
from __future__ import annotations

import time

import pytest

from atdd.coach.commands.coach import Phase, _check_no_progress_ttl


def test_no_progress_ttl_escalates_and_exits(tmp_path):
    escalation_log = tmp_path / "escalations.log"
    # Simulate last advance being 1000 seconds ago.
    last_advance_at = time.monotonic() - 1000

    result = _check_no_progress_ttl(
        last_advance_at=last_advance_at,
        no_progress_ttl_seconds=30,
        escalation_channel=str(escalation_log),
        issue_number=42,
        current_phase=Phase.RED,
    )

    assert result is True, "_check_no_progress_ttl must return True when TTL exceeded"
    assert escalation_log.exists(), "escalation must be written to the log file"
    content = escalation_log.read_text(encoding="utf-8")
    assert "42" in content, "escalation must mention the issue number"
    assert any(word in content.lower() for word in ("ttl", "self-terminat", "no progress")), (
        "escalation must mention TTL or self-termination"
    )


def test_no_progress_ttl_not_exceeded_returns_false(tmp_path):
    escalation_log = tmp_path / "escalations.log"
    last_advance_at = time.monotonic()  # just now — not exceeded

    result = _check_no_progress_ttl(
        last_advance_at=last_advance_at,
        no_progress_ttl_seconds=30,
        escalation_channel=str(escalation_log),
        issue_number=42,
        current_phase=Phase.RED,
    )

    assert result is False, "_check_no_progress_ttl must return False when TTL not exceeded"
    assert not escalation_log.exists(), "no escalation should be written when TTL not exceeded"
