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
someone to commit. Refs #1433 / #1400.
"""
from __future__ import annotations

import pytest

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import NondeterministicProjectionError, project

from ._helpers import memory_store

_CLEAN_UID = "wi_01HF7YAT00M78607F00000000C"
_TIMESTAMP_UID = "wi_01HF7YAT00M78607F00000000T"
_HOST_PATH_UID = "wi_01HF7YAT00M78607F00000000H"

_CLEAN = {"slug": "clean", "owner_actor": "dev-a", "state": "ACTIVE", "body": "no leaks here"}


def _project_with(conn, store, out_dir, uid, leaky_data):
    store.objects.upsert(_CLEAN_UID, WORK_ITEM_KIND, state="INIT", data=dict(_CLEAN))
    store.objects.upsert(uid, WORK_ITEM_KIND, state="INIT", data={**_CLEAN, **leaky_data})
    with pytest.raises(NondeterministicProjectionError) as caught:
        project(store, out_dir)
    return caught.value


def test_c001_unit_001_rejects_timestamp_and_host_path(tmp_path) -> None:
    """A generated_at timestamp and an absolute /Users/... path are each refused by name."""
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

    # A document that would carry an absolute host path.
    out_dir = tmp_path / "host-pathed"
    with memory_store() as (conn, store):
        error = _project_with(
            conn, store, out_dir, _HOST_PATH_UID,
            {"body": "store lives at /Users/alec/Github/atdd/.atdd/state/state.sqlite"},
        )
    assert error.field_path == "body"
    assert error.uid == _HOST_PATH_UID
    assert "host path" in str(error)

    # No projection file is written — not for the offending object, and not for the
    # clean one beside it. The refusal precedes every write.
    for out_dir in (tmp_path / "timestamped", tmp_path / "host-pathed"):
        assert not out_dir.exists() or list(out_dir.glob("*.yaml")) == []
