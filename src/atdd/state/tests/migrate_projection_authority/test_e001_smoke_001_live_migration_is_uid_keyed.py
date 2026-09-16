# URN: test:migrate-projection-authority:migrate-manifest-projection:E001-SMOKE-001-live-migration-is-uid-keyed
# Acceptance: acc:migrate-projection-authority:E001-SMOKE-001-live-migration-is-uid-keyed
# WMBT: wmbt:migrate-projection-authority:E001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state migrate-store` CLI mints an immutable uid and an owner_actor for every work item, the store then projects one document per work item keyed by that uid, and a second run is a no-op. Retargeted from `migrate-manifest` by #2023. Refs #1434, #2023.
"""SMOKE — the live migration is uid-keyed and idempotent (E001-SMOKE-001).

wagon: migrate-projection-authority | feature: migrate-manifest-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:E001

**Retargeted, not retired.** This acceptance drove `atdd state migrate-manifest --mint-uids`
against a populated `.atdd/manifest.yaml`. CORE-034 deleted that file, so the command could not run
and the acceptance asserted nothing (#2023).

E001's contract is about *identity*, not about the manifest: one deterministic document per work
item, keyed by an **immutable uid** rather than a mutable slug, so a rename moves nothing — and
minted in its own recorded step, so the tool that promises byte-identical re-runs is not the tool
that doubles the corpus. `atdd state migrate-store` is where that contract lives now. Refs #1434.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ._live import atdd_state, make_checkout

_LEGACY = (("alpha-thing", "PLANNED", 11), ("beta-thing", "GREEN", 12))


def _seed(root: Path) -> None:
    """A real slug-keyed store: no uid, no owner_actor — the pre-migration shape."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        for slug, phase, issue in _LEGACY:
            store.objects.upsert(
                slug, "work_item", state=phase, data={"title": slug.replace("-", " ")},
            )
            store.external_refs.link(slug, "github", "issue", str(issue), data={"source": "seed"})
        conn.commit()
    finally:
        conn.close()


def _uids(root: Path) -> list[str]:
    """Every work item uid, read back through a FRESH read-only connection to the on-disk store."""
    import sqlite3

    path = root / ".atdd" / "state" / "state.sqlite"
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return sorted(
            r[0] for r in conn.execute("SELECT uid FROM objects WHERE kind='work_item'")
        )
    finally:
        conn.close()


@pytest.mark.smoke
def test_e001_smoke_001_every_work_item_gains_an_immutable_uid(tmp_path) -> None:
    """Slug-keyed in, uid-keyed out — one per work item, none left behind."""
    repo = make_checkout(tmp_path / "repo")
    _seed(repo)
    assert all(not u.startswith("wi_") for u in _uids(repo)), "the given is not pre-migration"

    result = atdd_state(repo, "migrate-store")
    assert result.returncode == 0, result.stdout + result.stderr

    uids = _uids(repo)
    assert len(uids) == len(_LEGACY), f"expected one object per work item, got {uids}"
    assert all(u.startswith("wi_") for u in uids), f"not every work item is uid-keyed: {uids}"


@pytest.mark.smoke
def test_e001_smoke_001_the_projection_is_one_document_per_work_item(tmp_path) -> None:
    """The migrated store projects, and each document is named by its uid, never its slug."""
    repo = make_checkout(tmp_path / "repo")
    _seed(repo)
    assert atdd_state(repo, "migrate-store").returncode == 0

    out = repo / "projection-out"
    projected = atdd_state(repo, "project", "--out", str(out))
    assert projected.returncode == 0, projected.stdout + projected.stderr

    files = sorted(p.stem for p in out.glob("*.yaml"))
    assert len(files) == len(_LEGACY), f"expected one document per work item, got {files}"
    assert all(name.startswith("wi_") for name in files), f"a document is slug-named: {files}"
    assert files == _uids(repo), "the documents are not keyed by the store's uids"


@pytest.mark.smoke
def test_e001_smoke_001_a_second_run_mints_nothing_new(tmp_path) -> None:
    """Identity is minted once. A re-run that re-rolled it would double the corpus."""
    repo = make_checkout(tmp_path / "repo")
    _seed(repo)
    assert atdd_state(repo, "migrate-store").returncode == 0
    first = _uids(repo)

    second = atdd_state(repo, "migrate-store")
    assert second.returncode == 0, second.stdout + second.stderr
    assert _uids(repo) == first, (
        "the second run changed identity — the tool that promises byte-identical re-runs would be "
        "the tool that duplicates the corpus"
    )
