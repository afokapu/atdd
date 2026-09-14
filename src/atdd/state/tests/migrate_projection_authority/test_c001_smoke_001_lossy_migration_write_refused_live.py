# URN: test:migrate-projection-authority:migrate-manifest-projection:C001-SMOKE-001-lossy-migration-write-refused-live
# Acceptance: acc:migrate-projection-authority:C001-SMOKE-001-lossy-migration-write-refused-live
# WMBT: wmbt:migrate-projection-authority:C001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state migrate-store` CLI refuses the WHOLE run before any write when one object cannot be faithfully carried, names it, and leaves the store byte-identical. Retargeted from `migrate-manifest` by #2023. Refs #1434, #2023.
"""SMOKE — a lossy migration write is refused, live (C001-SMOKE-001).

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:C001

**Retargeted, not retired.** This acceptance drove `atdd state migrate-manifest`, whose input
`.atdd/manifest.yaml` CORE-034 deleted — so it asserted a contract through a command that could no
longer run. C001's contract did not go away with the verb: "refuse the whole run before writing
anything, and name every offender" is the posture the live migration inherited. So the acceptance
follows the contract to the verb that runs (#2023).

The refusal is the feature. A migration that half-succeeds leaves a store that is neither the old
truth nor the new one, and the operator's next move — re-run, revert, hand-fix — depends on facts
the tool destroyed on its way out. Refs #1434 / #2023.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ._live import atdd_state, make_checkout

#: A data key the projection contract has no disposition for — this is what poisons the run.
UNDISPOSITIONED_KEY = "cycle_time_p95"

_LEGACY = (("alpha-thing", "PLANNED", 11), ("beta-thing", "GREEN", 12))


def _seed(root: Path, *, poison: bool) -> None:
    """A real, slug-keyed, pre-migration store on disk; optionally carrying an unprojectable key."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore
    from atdd.state.store_migration import _DISPOSITIONED, _PROJECTABLE_DATA_FIELDS

    if poison:
        assert UNDISPOSITIONED_KEY not in _DISPOSITIONED | _PROJECTABLE_DATA_FIELDS, (
            f"{UNDISPOSITIONED_KEY!r} now has a disposition; this fixture needs one that has none"
        )
    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        for slug, phase, issue in _LEGACY:
            data = {"title": slug.replace("-", " ")}
            if poison and slug == "beta-thing":
                data[UNDISPOSITIONED_KEY] = 4.2
            store.objects.upsert(slug, "work_item", state=phase, data=data)
            store.external_refs.link(slug, "github", "issue", str(issue), data={"source": "seed"})
        conn.commit()
    finally:
        conn.close()


def _store_bytes(root: Path) -> bytes:
    return (root / ".atdd" / "state" / "state.sqlite").read_bytes()


@pytest.mark.smoke
def test_c001_smoke_001_one_bad_object_refuses_the_whole_run(tmp_path) -> None:
    """Non-zero, the offender named, and not one byte of the store changed."""
    repo = make_checkout(tmp_path / "repo")
    _seed(repo, poison=True)
    before = _store_bytes(repo)

    result = atdd_state(repo, "migrate-store")
    combined = result.stdout + result.stderr

    assert result.returncode != 0, f"a lossy migration was allowed to write:\n{combined}"
    assert UNDISPOSITIONED_KEY in combined, (
        f"the refusal does not name what stands in the way:\n{combined}"
    )
    assert _store_bytes(repo) == before, (
        "the store changed on a refused run — a half-applied migration is the state C001 exists "
        "to prevent"
    )


@pytest.mark.smoke
def test_c001_smoke_001_a_clean_corpus_is_not_refused(tmp_path) -> None:
    """The guard must bite only on the fault — a refusal that always fires proves nothing."""
    repo = make_checkout(tmp_path / "repo")
    _seed(repo, poison=False)
    result = atdd_state(repo, "migrate-store")
    assert result.returncode == 0, (
        f"a clean corpus was refused; the guard is not discriminating:\n{result.stdout}{result.stderr}"
    )
