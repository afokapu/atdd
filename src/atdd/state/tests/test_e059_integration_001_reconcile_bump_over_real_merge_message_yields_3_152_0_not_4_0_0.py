# URN: test:govern-lifecycle:state:E059-INTEGRATION-001-reconcile-bump-over-the-real-merge-message-yields-3-152-0-not-4-0-0
# Acceptance: acc:govern-lifecycle:E059-INTEGRATION-001-reconcile-bump-over-the-real-merge-message-yields-3-152-0-not-4-0-0
# WMBT: wmbt:govern-lifecycle:E059
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E059-INTEGRATION-001 — the CI reconcile->bump over the REAL merge message.

#1297. This is exactly the sequence the ``tag-release`` job ran on Publish run
28495533869: reconcile the store's current from the latest git tag (3.151.0),
then bump by the change class derived from the merge commit. Driven by the
ACTUAL #1285/#1291 merge message — a ``feat`` header whose body mentions
``BREAKING CHANGE`` only in descriptive prose — the pipeline must yield 3.152.0
(MINOR), NOT the 4.0.0 the run produced, and leave a single pending
``version_decided{3.152.0}`` message for the drain.
"""
from __future__ import annotations

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.store import StateStore
from atdd.state import version as ver

# The CI context that produced the bug: current is the latest git tag; the merge
# commit is the real #1285/#1291 message whose body PROSE mentions BREAKING CHANGE
# (verbatim fragment: "breaking !/BREAKING CHANGE=MAJOR, else PATCH").
_LATEST_TAG_VERSION = "3.151.0"
_REAL_MERGE_MESSAGE = (
    "feat(atdd): Wire release-worker extension into core publish pipeline "
    "(drain version_decided -> tag + PyPI) (#1285) (#1291)\n\n"
    "change_class_for_commit(subject) maps a conventional-commit type to\n"
    "PATCH/MINOR/MAJOR (feat=MINOR, breaking !/BREAKING CHANGE=MAJOR, else PATCH).\n"
)


@pytest.fixture()
def conn(tmp_path):
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    c = connect(db)
    try:
        yield c
    finally:
        c.close()


def test_real_merge_message_classifies_minor():
    # The prose mention must not escalate the feat to MAJOR.
    assert ver.change_class_for_commit(_REAL_MERGE_MESSAGE) == "MINOR"


def test_reconcile_bump_over_real_merge_message_resolves_3_152_0(conn):
    ver.set_version(conn, _LATEST_TAG_VERSION)
    ver.bump(conn, ver.change_class_for_commit(_REAL_MERGE_MESSAGE))

    resolved = ver.emit(conn)
    assert resolved == "3.152.0"            # MINOR over 3.151.0 — the correct next
    assert resolved != "4.0.0"              # NOT the run-28495533869 mis-bump
    assert resolved != ver.LOCAL_FALLBACK_VERSION


def test_reconcile_bump_leaves_single_pending_version_decided_3_152_0(conn):
    ver.set_version(conn, _LATEST_TAG_VERSION)
    ver.bump(conn, ver.change_class_for_commit(_REAL_MERGE_MESSAGE), provider="github")

    pending = StateStore(conn).sync.pending_outbox()
    assert len(pending) == 1
    msg = pending[0]
    assert msg.operation == ver.VERSION_DECIDED_OPERATION == "version_decided"
    assert msg.payload == {"version": "3.152.0", "change_class": "MINOR"}
