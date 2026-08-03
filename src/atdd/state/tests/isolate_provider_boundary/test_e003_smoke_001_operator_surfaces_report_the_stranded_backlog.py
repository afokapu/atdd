# URN: test:isolate-provider-boundary:surface-undrainable-outbox:E003-SMOKE-001-operator-surfaces-report-the-stranded-backlog
# Acceptance: acc:isolate-provider-boundary:E003-SMOKE-001-operator-surfaces-report-the-stranded-backlog
# WMBT: wmbt:isolate-provider-boundary:E003
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: In a real checkout, against a real .atdd/state/state.sqlite driven only through the installed atdd CLI, the surfaces that used to report health now report the stranded backlog: `atdd state providers` and `atdd state sync` name it, `atdd state outbox check` exits non-zero and names the count and routing key, and no surface offers a remedy no registered provider could perform. Refs #1655.
"""The sentence that used to sit on top of the backlog now names it (E003-SMOKE-001).

wagon: isolate-provider-boundary | feature: surface-undrainable-outbox | phase: SMOKE
WMBT: wmbt:isolate-provider-boundary:E003

#1655 was measured on a real store, so it is closed on one. The unit acceptances pin
the rule; this pins the thing an operator actually meets — real CLI, real SQLite, no
in-process patching — because the defect was never in the logic. It was in what the
commands *said*, and only running them proves what they say.

The negative assertion is the load-bearing one. ``atdd state sync`` used to answer a
non-empty outbox with "pass ``--push``". Withdrawing a remedy that cannot work
matters as much as adding the warning: an operator who follows stale advice into a
command that exits 1 forever has been failed twice.
"""
from __future__ import annotations

import pytest

from ._live import atdd_state, repo_on_bare_remote


def _enqueue(repo, provider: str, operation: str, payload: dict) -> None:
    """Queue one outbox row through the store the CLI itself initialised.

    Uses core's own SyncStore against the real on-disk database rather than raw SQL,
    so the row is shaped exactly like one a real bump or authoring failure leaves.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=repo))
    try:
        StateStore(conn).sync.enqueue_outbox(provider, operation, payload)
    finally:
        conn.close()


@pytest.mark.smoke
def test_e003_smoke_001_operator_surfaces_report_the_stranded_backlog(tmp_path) -> None:
    """A real store with unroutable rows: every operator surface says so, and check exits 1."""
    _remote, repo = repo_on_bare_remote(tmp_path)

    # Provider-free and idle: healthy, and it must still read as healthy.
    idle = atdd_state(repo, "outbox", "check")
    assert idle.returncode == 0, idle.stdout + idle.stderr
    assert "STRANDED" not in idle.stdout

    idle_sync = atdd_state(repo, "sync")
    assert idle_sync.returncode == 0, idle_sync.stdout + idle_sync.stderr

    # Now the condition #1655 found: decisions queued, nothing registered to route them.
    _enqueue(repo, "github", "version_decided", {"version": "4.23.0", "change_class": "MINOR"})
    _enqueue(repo, "github", "create_issue", {"title": "something that never got filed"})

    # 1. `atdd state outbox check` — the gateable primitive.
    check = atdd_state(repo, "outbox", "check")
    assert check.returncode == 1, "a stranded backlog must be non-zero, or nothing can gate on it"
    loud = check.stdout + check.stderr
    assert "STRANDED OUTBOX" in loud
    assert "2 of 2 pending" in loud
    assert "github (2)" in loud, "the routing key nothing is registered for must be named"

    # 2. `atdd state providers` — the exact command whose reassuring sentence #1655 quoted.
    provs = atdd_state(repo, "providers")
    assert provs.returncode == 0, provs.stdout + provs.stderr
    assert "no SyncProvider is registered" in provs.stdout, "still true, and still said"
    assert "STRANDED OUTBOX" in provs.stdout, "and no longer said on its own"

    # 3. `atdd state sync` — and the withdrawn remedy.
    sync = atdd_state(repo, "sync")
    assert sync.returncode == 0, sync.stdout + sync.stderr
    assert "STRANDED OUTBOX" in sync.stdout
    assert "pass --push" not in sync.stdout, (
        "--push cannot drain a row no registered provider claims; offering it is the "
        "second failure, after the silence"
    )

    # 4. `atdd state outbox list` — the rows themselves, with computed routability.
    listing = atdd_state(repo, "outbox", "list")
    assert listing.returncode == 0, listing.stdout + listing.stderr
    assert "version_decided" in listing.stdout and "create_issue" in listing.stdout
    assert "4.23.0" in listing.stdout, "a version decision names the version it decided"
    assert "NO" in listing.stdout, "each pending row is marked unroutable"


@pytest.mark.smoke
def test_e003_smoke_001_discard_needs_a_reason_and_clears_the_signal(tmp_path) -> None:
    """Through the real CLI: no reason, no discard — and a reasoned discard quiets the alarm."""
    _remote, repo = repo_on_bare_remote(tmp_path)
    _enqueue(repo, "github", "version_decided", {"version": "5.0.0", "change_class": "MAJOR"})

    # Refused without a reason, and the row is untouched.
    bare = atdd_state(repo, "outbox", "discard", "1")
    assert bare.returncode == 1
    assert "without --reason" in bare.stderr
    assert atdd_state(repo, "outbox", "check").returncode == 1, "still stranded"

    # Retired against a recorded reason.
    reason = "version 5.0.0 retracted by SET -> 4.22.0; superseded by v4.28.0"
    done = atdd_state(repo, "outbox", "discard", "1", "--reason", reason)
    assert done.returncode == 0, done.stdout + done.stderr

    # The signal clears, because the backlog genuinely did.
    assert atdd_state(repo, "outbox", "check").returncode == 0

    # And the decision is still on the record, with why it was retired.
    listing = atdd_state(repo, "outbox", "list")
    assert "discarded" in listing.stdout
    assert "retracted" in listing.stdout, "the reason survives in the listing, not just the row"
