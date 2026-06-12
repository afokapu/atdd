# URN: test:mediate-worker-decisions:feed-daemon-durability:R004-UNIT-002-read-decisions-skips-one-corrupt-line
# Acceptance: acc:mediate-worker-decisions:R004-UNIT-002-read-decisions-skips-one-corrupt-line
# WMBT: wmbt:mediate-worker-decisions:R004
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""R004-UNIT-002 — _read_decisions skips one corrupt tail line, never aborts.

``_read_decisions`` calls ``json.loads`` per line unguarded, mirroring the
``replay_events`` gap: one corrupt tail line makes every persisted decision
unreadable. It must adopt the same skip-one tolerance as
``_read_validator_reports``.

RED: today the corrupt line raises out of ``_read_decisions``. Fails until the
per-line guard lands.
"""
from __future__ import annotations

import pytest

from atdd.coach.core.types import Phase, TransitionDecision, Verdict, VerdictKind
from atdd.train.persistence import JsonlPersistenceStore, load_conventions

from tests.coach._e040_helpers import build_temp_repo

pytestmark = pytest.mark.atdd_validator


def _decision():
    return TransitionDecision(
        from_phase=Phase.GREEN,
        to_phase=Phase.SMOKE,
        persona=None,
        prompt_template_id=None,
        evidence_keys_required=(),
        verdict=Verdict(kind=VerdictKind.PROCEED, reason="ok", rule_ids=("r",)),
    )


def test_read_decisions_skips_one_corrupt_line(tmp_path):
    repo = build_temp_repo(tmp_path)
    conventions = load_conventions(repo)
    store = JsonlPersistenceStore(repo)
    run_id = store.create_run(894, conventions=conventions)

    store.append_decision(run_id, _decision(), evidence_hash="h")

    decisions_file = (
        repo / ".atdd" / "runtime" / "runs" / str(run_id) / "decisions.jsonl"
    )
    valid_before = [
        line for line in decisions_file.read_text().splitlines() if line.strip()
    ]
    assert len(valid_before) == 1

    # Append a corrupt tail line.
    with decisions_file.open("a", encoding="utf-8") as fh:
        fh.write('{"evidence_hash": "h", "decision": {oops')  # malformed

    # Skip-one tolerance: every valid decision is returned with no raise.
    decisions = list(store._read_decisions(run_id))

    assert len(decisions) == 1, (
        "_read_decisions failed to skip the corrupt tail line and recover the "
        "valid decision"
    )
    assert decisions[0].verdict.kind == VerdictKind.PROCEED
