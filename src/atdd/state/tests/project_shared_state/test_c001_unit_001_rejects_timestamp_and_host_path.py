# URN: test:project-shared-state:project-store:C001-UNIT-001-rejects-timestamp-and-host-path
# Acceptance: acc:project-shared-state:C001-UNIT-001-rejects-timestamp-and-host-path
# WMBT: wmbt:project-shared-state:C001
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A projection document that would carry a generated_at timestamp or an absolute /Users/... host path is refused before any write — the error names the offending field and no file appears. Refs #1433.
"""Determinism leaks are refused before the first byte (C001-UNIT-001).

wagon: project-shared-state | feature: project-store | phase: RED
WMBT: wmbt:project-shared-state:C001

A wall-clock timestamp or a host path in a committed projection is a diff every
peer sees and nobody authored. The guard must fire *before* the write: a projection
half-applied and then rolled back would still leave the offending file on disk for
someone to commit.

The guard scans the fields the **projector generates** — that is where a timestamp
or a host path means the projector reached for the wall clock or the local
filesystem, which is the fault I1 names. The free-text ``body`` is exempt from the
value scan: a human who quotes a path or a date in their prose has authored fixed
content, which the projector copies byte for byte on every host and every run. It
is deterministic by preservation, and refusing it would refuse a legal issue body
while catching no leak at all. That exemption is asserted here too, so the
narrowing is a property of the suite and not a silent hole in it.
Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import NondeterministicProjectionError, project

from ._helpers import memory_store

_CLEAN_UID = "wi_01HF7YAT00M78607F00000000C"
_TIMESTAMP_UID = "wi_01HF7YAT00M78607F00000000T"
_HOST_PATH_UID = "wi_01HF7YAT00M78607F00000000H"
_PROSE_UID = "wi_01HF7YAT00M78607F00000000P"

_CLEAN = {"slug": "clean", "owner_actor": "dev-a", "state": "ACTIVE", "body": "no leaks here"}

#: The path an issue body plausibly quotes, and the one the projector must never inject.
_HOST_PATH = "/Users/alec/Github/atdd/.atdd/state/state.sqlite"


def _upsert(store, uid, leaky_data):
    store.objects.upsert(uid, WORK_ITEM_KIND, state="INIT", data={**_CLEAN, **leaky_data})


def _project_with(conn, store, out_dir, uid, leaky_data):
    store.objects.upsert(_CLEAN_UID, WORK_ITEM_KIND, state="INIT", data=dict(_CLEAN))
    _upsert(store, uid, leaky_data)
    with pytest.raises(NondeterministicProjectionError) as caught:
        project(store, out_dir)
    return caught.value


def test_c001_unit_001_rejects_timestamp_and_host_path(tmp_path) -> None:
    """A generated_at timestamp and a host path in a generated field are refused by name."""
    # A document that would carry a wall-clock timestamp.
    out_dir = tmp_path / "timestamped"
    with memory_store() as (conn, store):
        error = _project_with(
            conn, store, out_dir, _TIMESTAMP_UID,
            {"generated_at": "2026-07-11T09:41:02"},
        )
    assert error.field_path == "generated_at"
    assert error.uid == _TIMESTAMP_UID
    assert "generated_at" in str(error)

    # A document whose machine-written ``external_refs`` subtree would carry the
    # absolute path of this developer's own store — the host-path leak that actually
    # happens, in a field the projector generates rather than preserves.
    out_dir = tmp_path / "host-pathed"
    with memory_store() as (conn, store):
        error = _project_with(
            conn, store, out_dir, _HOST_PATH_UID,
            {"external_refs": {"mirror_path": _HOST_PATH}},
        )
    assert error.field_path == "external_refs.mirror_path"
    assert error.uid == _HOST_PATH_UID
    assert "host path" in str(error)

    # No projection file is written — not for the offending object, and not for the
    # clean one beside it. The refusal precedes every write.
    for out_dir in (tmp_path / "timestamped", tmp_path / "host-pathed"):
        assert not out_dir.exists() or list(out_dir.glob("*.yaml")) == []

    # ...and the narrowing itself: the very same path and the very same date, written
    # by a human into the free-text body, project cleanly and reproduce byte-identically.
    out_dir = tmp_path / "prose"
    prose = f"Repro: the store at {_HOST_PATH} was corrupted on 2026-07-11T09:41:02."
    with memory_store() as (conn, store):
        _upsert(store, _PROSE_UID, {"body": prose})
        first = project(store, out_dir).files[_PROSE_UID].read_bytes()
        second = project(store, tmp_path / "prose-again").files[_PROSE_UID].read_bytes()
    assert first == second
    assert prose in first.decode("utf-8")
