# URN: test:project-shared-state:project-store:C001-SMOKE-001-nondeterministic-projection-content
# Acceptance: acc:project-shared-state:C001-SMOKE-001-nondeterministic-projection-content
# WMBT: wmbt:project-shared-state:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state project` CLI, run against a real store holding a timestamp/host-path leak, exits non-zero naming the offending field and writes no projection file; and a real projection carries no timestamp or host path at all. Refs #1433.
"""SMOKE — nondeterministic content never reaches a real projection file (C001-SMOKE-001).

wagon: project-shared-state | feature: project-store | phase: SMOKE
WMBT: wmbt:project-shared-state:C001

The unit guard proves the serializer refuses a leak. This proves the *shipped
command* refuses it too — against a real checkout, a real state.sqlite, and the real
``.atdd/state/projection/`` directory an operator would then commit. The leak here is
the one that actually happens: the absolute path of the developer's own store.
Refs #1433 / #1400.
"""
from __future__ import annotations

import sqlite3

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.projection import _HOST_PATH_RE, _TIMESTAMP_VALUE_RE
from atdd.state.store import StateStore

from ._live import atdd_state, make_checkout


def test_c001_smoke_001_nondeterministic_projection_content(tmp_path) -> None:
    """The real CLI refuses a leaky store by name, writes nothing, and stays clean otherwise."""
    repo = make_checkout(tmp_path / "repo")
    assert atdd_state(repo, "init").returncode == 0

    created = atdd_state(repo, "object", "create", "--slug", "feature-x",
                         "--owner", "dev-a", "--body", "clean body")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip()

    # A real projection of a clean real store carries no timestamp and no host path.
    projected = atdd_state(repo, "project")
    assert projected.returncode == 0, projected.stderr
    projection = repo / ".atdd" / "state" / "projection"
    text = (projection / f"{uid}.yaml").read_text(encoding="utf-8")
    assert not _TIMESTAMP_VALUE_RE.search(text), text
    assert not _HOST_PATH_RE.search(text), text
    assert str(repo) not in text

    # Now plant each real-world leak in the real store, one at a time, and prove the
    # shipped command refuses each by name. (Both at once would only ever name the
    # first — the guard reports the field it must be told about, not a list.)
    before = (projection / f"{uid}.yaml").read_bytes()

    # Leak 1: a wall-clock reading.
    _plant(repo, uid, {"generated_at": "2026-07-11T09:41:02"})
    refused = atdd_state(repo, "project")
    assert refused.returncode != 0, refused.stdout
    assert "nondeterministic projection content" in refused.stdout
    assert "generated_at" in refused.stdout
    assert "wall-clock timestamp" in refused.stdout

    # Leak 2: the absolute path of the developer's own store — the leak that
    # actually happens.
    store_path = repo / ".atdd" / "state" / "state.sqlite"
    _plant(repo, uid, {"generated_at": None, "body": f"store lives at {store_path}"})
    refused = atdd_state(repo, "project")
    assert refused.returncode != 0, refused.stdout
    assert "'body'" in refused.stdout
    assert "absolute host path" in refused.stdout

    # Through both refusals the previously written file is untouched: the guard runs
    # before every write, so a leaky store never leaves a half-applied projection.
    assert (projection / f"{uid}.yaml").read_bytes() == before


def _plant(repo, uid, fields) -> None:
    """Write ``fields`` straight into the real store, bypassing the CLI's own guards."""
    conn = sqlite3.connect(str(repo / ".atdd" / "state" / "state.sqlite"))
    conn.row_factory = sqlite3.Row
    try:
        store = StateStore(conn)
        obj = store.objects.get(uid)
        assert obj is not None
        data = {**obj.data, **fields}
        store.objects.upsert(
            uid, WORK_ITEM_KIND, state=obj.state,
            data={k: v for k, v in data.items() if v is not None},
        )
    finally:
        conn.close()
