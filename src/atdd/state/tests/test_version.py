# URN: test:state-store:version:release-source-of-truth
# Issue: #1172 (State Store owns version source-of-truth)
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""#1172 — the State Store as the release-version source of truth.

Covers current/emit/next_from_change_class/bump semantics, the version_bumped
event audit trail, the provider-neutral ``version_decided`` outbox signal emitted
on a bump (#1172 design-doc §2/§3 boundary), the release_projection read view,
and the no-store fallback contract shared with the build hook.
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
# bump — writes object + appends event + emits the neutral decision signal
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
# version_decided — provider-neutral decision signal (core decides, extension
# publishes). Pins the #1172 design-doc §2/§3 boundary: core names no provider's
# publish mechanics — operation + payload are neutral; only outbox routing is
# provider-configured.
# --------------------------------------------------------------------------- #
def test_bump_emits_neutral_version_decided_signal(conn):
    ver.bump(conn, "MINOR", pr="1172")               # -> 3.150.0

    store = StateStore(conn)
    pending = store.sync.pending_outbox()
    assert len(pending) == 1
    msg = pending[0]

    # Operation name is neutral — NOT "tag_and_publish"/"publish"/anything provider-y.
    assert msg.operation == ver.VERSION_DECIDED_OPERATION == "version_decided"
    # Payload carries ONLY {version, change_class} — no "tag", no provider ref.
    assert msg.payload == {"version": "3.150.0", "change_class": "MINOR"}
    assert "tag" not in msg.payload


def test_core_writes_no_git_tag_external_ref(conn):
    """The git-tag external_ref is the extension's inbox writeback, never core's."""
    ver.bump(conn, "MINOR")                          # -> 3.150.0
    store = StateStore(conn)
    # Core must NOT have linked any release/tag ref on a bump.
    assert store.external_refs.resolve("github", "tag", "v3.150.0") is None
    assert store.external_refs.for_object("release") == []


def test_core_names_no_publish_mechanics(conn):
    """Source-level guard: core's signal names no provider publish mechanics.

    Core may *route* to a configured provider, but it must not (a) name a publish
    operation, nor (b) use :class:`ExternalRefStore` — the git-tag writeback that
    is the extension's inbox job, never core's.
    """
    import inspect
    src = inspect.getsource(ver)
    assert "tag_and_publish" not in src
    assert "ExternalRefStore" not in src        # core writes no provider ref
    assert ver.VERSION_DECIDED_OPERATION == "version_decided"


def test_bump_outbox_provider_is_configurable(conn):
    """`provider` is a configured routing value, not provider logic baked into core."""
    ver.bump(conn, "PATCH", provider="npmjs")
    msg = StateStore(conn).sync.pending_outbox()[0]
    assert msg.provider == "npmjs"
    # Operation + payload stay neutral regardless of routing target.
    assert msg.operation == "version_decided"
    assert "tag" not in msg.payload
