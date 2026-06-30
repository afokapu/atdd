# URN: test:state-store:version:release-source-of-truth
# Issue: #1172 (State Store owns version source-of-truth)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1172 — the State Store as the release-version source of truth.

Covers current/emit/next_from_change_class/bump semantics, the version_bumped
event audit trail, the publish_release outbox enqueue, the release_projection
read view, and the no-store fallback contract shared with the build hook.
"""
from __future__ import annotations

import pytest

from atdd.state.db import connect, init_state_store
from atdd.state.migrations import RELEASE_SEED_VERSION
from atdd.state.projections import VERSION_BUMPED_EVENT, release_projection
from atdd.state.store import ObjectStore, StateStore
from atdd.state import version as ver


@pytest.fixture()
def conn(tmp_path):
    db = init_state_store(db_path=tmp_path / ".atdd" / "state" / "state.sqlite")
    c = connect(db)
    try:
        yield c
    finally:
        c.close()


# --------------------------------------------------------------------------- #
# parse / next
# --------------------------------------------------------------------------- #
def test_parse_semver_core_and_suffixes():
    assert ver.parse("3.149.0") == (3, 149, 0)
    assert ver.parse("0.0.0+local") == (0, 0, 0)      # local segment ignored
    assert ver.parse("1.2.3-rc1") == (1, 2, 3)


def test_parse_rejects_non_semver():
    with pytest.raises(ver.VersionError):
        ver.parse("not-a-version")


@pytest.mark.parametrize("cls,expected", [
    ("PATCH", "3.149.1"),
    ("MINOR", "3.150.0"),
    ("MAJOR", "4.0.0"),
    ("patch", "3.149.1"),   # case-insensitive
])
def test_next_from_change_class(conn, cls, expected):
    assert ver.current(conn) == RELEASE_SEED_VERSION  # seeded baseline
    assert ver.next_from_change_class(conn, cls) == expected


def test_next_rejects_unknown_class(conn):
    with pytest.raises(ver.VersionError):
        ver.next_from_change_class(conn, "TINY")


# --------------------------------------------------------------------------- #
# current / emit / fallback
# --------------------------------------------------------------------------- #
def test_current_returns_seed(conn):
    assert ver.current(conn) == RELEASE_SEED_VERSION


def test_emit_falls_back_when_no_release_object(conn):
    ObjectStore(conn).delete("release")
    with pytest.raises(ver.VersionError):
        ver.current(conn)
    assert ver.emit(conn) == ver.LOCAL_FALLBACK_VERSION == "0.0.0+local"


# --------------------------------------------------------------------------- #
# bump — writes object + appends event
# --------------------------------------------------------------------------- #
def test_bump_writes_object_and_appends_event(conn):
    new = ver.bump(conn, "MINOR", pr="1172")
    assert new == "3.150.0"
    assert ver.current(conn) == "3.150.0"            # authoritative object updated

    events = StateStore(conn).events.list(object_uid="release")
    bumps = [e for e in events if e.event_type == VERSION_BUMPED_EVENT]
    assert len(bumps) == 1
    assert bumps[0].payload == {
        "from": RELEASE_SEED_VERSION, "to": "3.150.0",
        "change_class": "MINOR", "pr": "1172",
    }


def test_successive_bumps_chain(conn):
    assert ver.bump(conn, "PATCH") == "3.149.1"
    assert ver.bump(conn, "PATCH") == "3.149.2"
    assert ver.bump(conn, "MAJOR") == "4.0.0"
    assert ver.current(conn) == "4.0.0"


# --------------------------------------------------------------------------- #
# release_projection
# --------------------------------------------------------------------------- #
def test_release_projection_summarizes_bumps(conn):
    assert release_projection(conn).version == RELEASE_SEED_VERSION
    assert release_projection(conn).bump_count == 0

    ver.bump(conn, "MINOR", pr="1172")
    row = release_projection(conn)
    assert row.version == "3.150.0"
    assert row.bump_count == 1
    assert row.last_bump["to"] == "3.150.0"


def test_release_projection_none_without_object(conn):
    ObjectStore(conn).delete("release")
    assert release_projection(conn) is None


# --------------------------------------------------------------------------- #
# publish_release — outbox enqueue (core decides, extension publishes)
# --------------------------------------------------------------------------- #
def test_publish_release_enqueues_outbox_and_links_tag(conn):
    ver.bump(conn, "MINOR")                          # -> 3.150.0
    outbox_id = ver.publish_release(conn)
    assert isinstance(outbox_id, int)

    store = StateStore(conn)
    pending = store.sync.pending_outbox()
    assert len(pending) == 1
    msg = pending[0]
    assert msg.provider == "github"
    assert msg.operation == "tag_and_publish"
    assert msg.payload == {"version": "3.150.0", "tag": "v3.150.0"}

    ref = store.external_refs.resolve("github", "tag", "v3.150.0")
    assert ref is not None and ref.object_uid == "release"


def test_publish_release_accepts_explicit_version(conn):
    ver.publish_release(conn, "9.9.9")
    pending = StateStore(conn).sync.pending_outbox()
    assert pending[0].payload == {"version": "9.9.9", "tag": "v9.9.9"}
