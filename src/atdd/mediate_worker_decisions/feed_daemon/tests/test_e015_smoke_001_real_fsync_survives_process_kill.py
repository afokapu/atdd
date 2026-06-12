# URN: test:mediate-worker-decisions:feed-daemon-durability:E015-SMOKE-001-real-fsync-survives-process-kill
# Acceptance: acc:mediate-worker-decisions:E015-SMOKE-001-real-fsync-survives-process-kill
# WMBT: wmbt:mediate-worker-decisions:E015
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""E015-SMOKE-001 — a record committed by a process hard-killed right after the
append returns is still fully on disk.

Drives the REAL ``append_jsonl`` in a real child process that is killed with
SIGKILL the moment the append returns, then re-reads the ledger from the parent
and asserts the committed record is present and whole.

The harness is real. The fsync-vs-page-cache durability difference is only
observable under an OS-level crash / power loss (a process SIGKILL still leaves
flushed bytes in the OS page cache), which is not inducible in this environment —
so this smoke is skipped until run on infrastructure that can fault the OS. The
crash-safety contract is exercised hermetically by E015-UNIT-001/002.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.skip(
    reason="fsync durability is only falsifiable under an OS crash / power loss; "
    "a process SIGKILL does not lose OS-page-cache-flushed bytes. Real-crash "
    "infra not inducible here — hermetic coverage in E015-UNIT-001/002 (B1)."
)


def test_real_fsync_survives_process_kill(tmp_path):
    from atdd.mediate_worker_decisions.feed_daemon.live_smoke import (
        fsync_survives_kill_smoke,
    )

    evidence = fsync_survives_kill_smoke(tmp_path)
    assert evidence["record_present"] is True
    assert evidence["truncated"] is False
