# URN: test:mediate-worker-decisions:feed-daemon-durability:R004-UNIT-001-replay-skips-one-corrupt-line
# Acceptance: acc:mediate-worker-decisions:R004-UNIT-001-replay-skips-one-corrupt-line
# WMBT: wmbt:mediate-worker-decisions:R004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""R004-UNIT-001 — replay_events skips one corrupt tail line, never aborts the run.

``replay_events`` calls ``json.loads`` on every line unguarded, so one truncated
tail line (a crash can still leave one, even with the E015 write fix) raises and
makes the whole run unreplayable. ``_read_validator_reports`` already guards each
line with ``try/except json.JSONDecodeError`` and skips it — ``replay_events``
must adopt the same skip-one tolerance.

RED: today the corrupt line raises ``json.JSONDecodeError`` out of
``replay_events``. Fails until the per-line guard lands.
"""
from __future__ import annotations

import pytest

from atdd.train.persistence import JsonlPersistenceStore, load_conventions

from tests.coach._e040_helpers import build_temp_repo

pytestmark = pytest.mark.atdd_validator


def test_replay_skips_one_corrupt_line(tmp_path):
    repo = build_temp_repo(tmp_path)
    conventions = load_conventions(repo)
    store = JsonlPersistenceStore(repo)
    run_id = store.create_run(894, conventions=conventions)  # writes 1 valid RunStarted

    events_file = repo / ".atdd" / "runtime" / "runs" / str(run_id) / "events.jsonl"
    valid_before = [
        line for line in events_file.read_text().splitlines() if line.strip()
    ]
    assert len(valid_before) >= 1, "create_run should leave at least one valid event"

    # Append a truncated/corrupt tail line — the exact crash residue R004 defends.
    with events_file.open("a", encoding="utf-8") as fh:
        fh.write('{"schema_version": "1.0", "ts": "2026-')  # no closing brace / newline

    # Replay must skip the corrupt line and yield every well-formed event — no raise.
    events = list(store.replay_events(run_id))

    assert len(events) == len(valid_before), (
        "replay_events dropped or duplicated a valid event while tolerating the "
        "corrupt tail line"
    )
    assert events[0].type == "RunStarted"
