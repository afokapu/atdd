# URN: test:govern-projection-fields:mark-object-tombstone:K001-SMOKE-001-tombstoned-object-resurrection
# Acceptance: acc:govern-projection-fields:K001-SMOKE-001-tombstoned-object-resurrection
# WMBT: wmbt:govern-projection-fields:K001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: end-to-end against a real store, real commits and a real `git merge`: `atdd state author tombstone` retires an object into the projection as state TOMBSTONED with a reason digest and no file removed, a stale branch that sets a live phase on that uid is refused by the driver with a resurrection conflict naming the uid, the file survives the refusal, and `atdd state compact-archive` is the only thing that removes it Refs #1400.
"""The tombstone survives a real merge from a stale branch (K001-SMOKE-001).

wagon: govern-projection-fields | feature: mark-object-tombstone | phase: SMOKE
WMBT: wmbt:govern-projection-fields:K001

The whole lifecycle, live: a real object in a real ``.atdd/state/state.sqlite``, retired
through the real CLI, projected by the real projector, and then attacked by the case that
actually happens — a colleague who forked before the retirement and has been working ever
since, whose branch says the object is alive and moving.

Git runs the driver, the driver refuses, and the file is still there afterwards. Removing it
takes a deliberate archival act, which is the one operation that can.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.state.projection import STATE_TOMBSTONED, canonical_bytes
from atdd.state.tombstone import reason_digest

from ._live import (
    atdd_state,
    branch,
    checkout_branch,
    commit,
    merge,
    projection_file,
    repo_on_bare_remote,
)

REASON = "superseded by the projection model"


@pytest.mark.smoke
def test_k001_smoke_001_tombstoned_object_resurrection(tmp_path) -> None:
    """Retire for real, then watch a stale branch fail to bring it back."""
    _remote, repo = repo_on_bare_remote(tmp_path)
    assert atdd_state(repo, "init").returncode == 0

    created = atdd_state(repo, "object", "create", "--slug", "feature-x", "--owner", "dev-a")
    assert created.returncode == 0, created.stderr
    uid = created.stdout.strip().split()[0]
    assert atdd_state(repo, "project").returncode == 0
    live = yaml.safe_load(projection_file(repo, uid).read_text(encoding="utf-8"))
    commit(repo, "feat: mint feature-x")

    # The stale branch: forked while the object was still alive, and moving it along.
    branch(repo, "stale")
    projection_file(repo, uid).write_bytes(canonical_bytes({**live, "phase": "SMOKE"}))
    commit(repo, "feat: keep working on feature-x")

    # Meanwhile, on main: retire it, through the real authoring command and the real projector.
    checkout_branch(repo, "main")
    retired = atdd_state(repo, "author", "tombstone", uid, "--reason", REASON)
    assert retired.returncode == 0, retired.stderr
    assert atdd_state(repo, "project").returncode == 0

    record = yaml.safe_load(projection_file(repo, uid).read_text(encoding="utf-8"))
    assert record["state"] == STATE_TOMBSTONED
    assert record["tombstone"]["reason"] == REASON
    assert record["tombstone"]["reason_digest"] == reason_digest(REASON)
    assert projection_file(repo, uid).is_file(), "retirement removed no file"
    commit(repo, "chore: retire feature-x")

    # The merge that would bring it back to life.
    revival = merge(repo, "stale")

    assert revival.returncode != 0, "a tombstoned uid must not be revivable by a merge"
    report = revival.stdout + revival.stderr
    assert uid in report, "the report names the uid that was nearly revived"
    assert "TOMBSTONED" in report
    assert "no merge may revive" in report

    # The tombstoned projection file is still on disk, still the record.
    surviving = yaml.safe_load(projection_file(repo, uid).read_text(encoding="utf-8"))
    assert surviving["state"] == STATE_TOMBSTONED
    assert surviving["tombstone"]["reason_digest"] == reason_digest(REASON)

    from ._live import git

    git(repo, "merge", "--abort")

    # Physical removal exists — as an archival act, through its own command, and nowhere else.
    compacted = atdd_state(repo, "compact-archive", "--uid", uid)
    assert compacted.returncode == 0, compacted.stderr
    assert uid in compacted.stdout
    assert not projection_file(repo, uid).exists()
