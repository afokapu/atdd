# URN: test:govern-lifecycle:state:E058-INTEGRATION-001-reconcile-then-bump-yields-real-version-and-pending-drain
# Acceptance: acc:govern-lifecycle:E058-INTEGRATION-001-reconcile-then-bump-yields-real-version-and-pending-drain
# WMBT: wmbt:govern-lifecycle:E058
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E058-INTEGRATION-001 — reconcile->bump yields a real version + a pending drain.

#1285 / #1172 step 5. This is exactly the sequence the rewired publish job runs
in one CI job over an ephemeral store: reconcile the authoritative current from
the latest git tag, then bump by the change class derived from the merge commit.
The result must be a REAL version (not the 0.0.0+local skip fallback) AND a
single pending provider-neutral ``version_decided`` message routed to the
configured provider — proving CI would DRAIN through the release extension
rather than skip.
"""
from __future__ import annotations

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore
from atdd.state import version as ver

# Stand-ins for the CI context: the latest git tag and the merge commit subject.
_LATEST_TAG_VERSION = "3.151.0"
_MERGE_COMMIT_SUBJECT = "feat(atdd): wire release-worker extension into core publish"


@pytest.fixture()
def conn(tmp_path):
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    c = connect(db)
    try:
        yield c
    finally:
        c.close()


def test_reconcile_then_bump_yields_real_version(conn):
    ver.set_version(conn, _LATEST_TAG_VERSION)
    change_class = ver.change_class_for_commit(_MERGE_COMMIT_SUBJECT)
    ver.bump(conn, change_class)

    resolved = ver.emit(conn)
    assert resolved == "3.152.0"                       # feat over 3.151.0 -> MINOR
    assert resolved != ver.LOCAL_FALLBACK_VERSION      # NOT the 0.0.0+local skip


def test_reconcile_then_bump_leaves_a_pending_neutral_drain(conn):
    ver.set_version(conn, _LATEST_TAG_VERSION)
    ver.bump(conn, ver.change_class_for_commit(_MERGE_COMMIT_SUBJECT), provider="github")

    pending = StateStore(conn).sync.pending_outbox()
    assert len(pending) == 1
    msg = pending[0]
    assert msg.operation == ver.VERSION_DECIDED_OPERATION == "version_decided"
    assert msg.provider == "github"
    assert msg.payload == {"version": "3.152.0", "change_class": "MINOR"}
    assert "tag" not in msg.payload                    # core names no publish mechanics
