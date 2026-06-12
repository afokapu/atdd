# URN: test:mediate-worker-decisions:feed-daemon-durability:E015-UNIT-001-append-returns-only-after-record-is-durable
# Acceptance: acc:mediate-worker-decisions:E015-UNIT-001-append-returns-only-after-record-is-durable
# WMBT: wmbt:mediate-worker-decisions:E015
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E015-UNIT-001 — a successful append_jsonl is durable before it returns.

The shared ``append_jsonl`` backs ``escalations.jsonl`` and ``verdicts.jsonl``.
Today it opens in append mode and writes a line with NO flush/fsync/atomic
boundary, so a crash can lose the just-committed record. A durable append must
perform a durability syscall — ``os.fsync`` (force the bytes to disk) or
``os.replace`` (atomic commit, the FileCursorStore pattern) — before returning.

RED: the current implementation calls neither, so the record round-trips in the
happy path but is not crash-durable. Fails until the durable-write lands.
"""
from __future__ import annotations

import json
import os

from atdd.mediate_worker_decisions.commons.jsonl_writer import append_jsonl


def test_append_performs_a_durability_sync(tmp_path, monkeypatch):
    ledger = tmp_path / "verdicts.jsonl"

    fsync_calls: list[int] = []
    replace_calls: list[tuple] = []

    real_fsync = os.fsync
    real_replace = os.replace

    def _spy_fsync(fd):
        fsync_calls.append(fd)
        return real_fsync(fd)

    def _spy_replace(src, dst, *a, **k):
        replace_calls.append((src, dst))
        return real_replace(src, dst, *a, **k)

    monkeypatch.setattr(os, "fsync", _spy_fsync)
    monkeypatch.setattr(os, "replace", _spy_replace)

    append_jsonl(ledger, {"request_id": "req-1", "v": "alpha"})

    # The happy-path content must still be correct: one whole, parseable line.
    lines = ledger.read_text(encoding="utf-8").splitlines()
    assert lines == [json.dumps({"request_id": "req-1", "v": "alpha"}, ensure_ascii=False)]
    assert json.loads(lines[0])["request_id"] == "req-1"

    # Durability contract: a returned append must have forced the record to
    # stable storage via fsync OR committed it atomically via os.replace.
    assert fsync_calls or replace_calls, (
        "append_jsonl returned without any durability syscall (os.fsync / "
        "os.replace) — a crash can lose the committed record (B1)"
    )
