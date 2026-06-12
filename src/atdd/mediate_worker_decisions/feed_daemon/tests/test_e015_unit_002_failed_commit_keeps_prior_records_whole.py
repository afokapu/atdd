# URN: test:mediate-worker-decisions:feed-daemon-durability:E015-UNIT-002-crash-after-append-keeps-prior-records-whole
# Acceptance: acc:mediate-worker-decisions:E015-UNIT-002-crash-after-append-keeps-prior-records-whole
# WMBT: wmbt:mediate-worker-decisions:E015
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E015-UNIT-002 — a failed atomic commit leaves prior records whole, no half-line.

The durable append must be all-or-nothing: if the atomic commit point fails
(simulated here by ``os.replace`` raising), the previously committed records
remain intact and individually parseable, and the ledger carries NO truncated
half-line for the record that did not commit.

RED: the current append-mode writer never reaches ``os.replace`` — it writes the
new line straight into the live ledger — so injecting a commit failure has no
all-or-nothing effect: the partial/uncommitted record lands anyway. Fails until
the atomic temp+os.replace write (the FileCursorStore pattern) lands.
"""
from __future__ import annotations

import json
import os

import pytest

from atdd.mediate_worker_decisions.commons.jsonl_writer import append_jsonl


def test_failed_commit_keeps_prior_records_whole(tmp_path, monkeypatch):
    ledger = tmp_path / "escalations.jsonl"

    # N already-committed records (written before the fault is injected).
    prior = [{"request_id": f"req-{i}", "n": i} for i in range(3)]
    for rec in prior:
        append_jsonl(ledger, rec)

    before = ledger.read_text(encoding="utf-8")

    # Inject a crash at the atomic commit point: the durable writer commits via
    # os.replace, so a raising os.replace models a crash *before* the new record
    # is durably swapped in.
    def _boom(src, dst, *a, **k):
        raise OSError("simulated crash at commit point")

    monkeypatch.setattr(os, "replace", _boom)

    # An append whose commit fails must NOT silently succeed — it raises rather
    # than returning with a half-written ledger.
    with pytest.raises(Exception):
        append_jsonl(ledger, {"request_id": "req-doomed", "n": 99})

    # All N prior records survive intact and each parses cleanly.
    lines = ledger.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert [r["request_id"] for r in parsed] == ["req-0", "req-1", "req-2"], (
        "a failed commit corrupted or dropped previously committed records"
    )

    # No truncated half-line for the uncommitted record.
    assert "req-doomed" not in ledger.read_text(encoding="utf-8"), (
        "the uncommitted record leaked a partial line into the live ledger (B1)"
    )
    assert ledger.read_text(encoding="utf-8") == before, (
        "the live ledger changed despite the commit failing — not all-or-nothing"
    )
