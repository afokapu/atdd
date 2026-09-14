# URN: test:migrate-projection-authority:migrate-store-projection:C003-SMOKE-001-no-destructive-write
# Acceptance: acc:migrate-projection-authority:C003-SMOKE-001-no-destructive-write
# WMBT: wmbt:migrate-projection-authority:C003
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end through the shipped `atdd state project` and `atdd state hydrate` against a real checkout and a real store: an inbound ingest destroys no locally-held state — not the stripped keys, not a bot-written ref the table cannot source, not a ref row's provenance blob. Refs #2025.
"""An inbound ingest destroys nothing (C003-SMOKE-001).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:C003

The unit acceptances pin each preservation property against an in-process store. This one
runs the real operator motion — `atdd state project`, then `atdd state hydrate` back over
the SAME store, through the shipped verbs — and checks all three at once, because that is
how they will actually be met: one ingest, touching every write path in sequence.

Three things must survive it, each destroyed by a different replace-where-merge-was-required
fault:

  - `branch` and `feature` in the data bag   — `ObjectStore.upsert` is `data=excluded.data`
  - `github.pr` and `jira.ticket`            — a projector that rebuilds the ref subtree
  - a ref row's `data` blob                  — `link()` is `DO UPDATE SET data=excluded.data`

`check_canonicality` cannot stand in for any of this: it hydrates into an EMPTY MemoryStore,
so there is nothing there to destroy and it reports canonical throughout.

HERMETIC on the same three pins as the other SMOKE in this wagon: `--root`, `HOME` and
`PYTHONPATH` inside `tmp_path`. The shared Control Root store is never opened.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ._live import atdd_state, make_checkout

pytestmark = [pytest.mark.platform]

_GITHUB, _ISSUE, _PR = "github", "issue", "pr"
_ISSUE_NUMBER = 9201

#: Machine-local state the projection deliberately strips and must not delete.
_LOCAL = {"branch": "feat/live-no-destructive-write", "feature": "feature:w:f", "worktree": "wt-live"}
#: Bot-written refs the external_refs table cannot source.
_BOT_REFS = {_GITHUB: {_PR: "2028"}, "jira": {"ticket": "ATDD-17"}}
#: Provenance on the ref row itself.
_PROVENANCE = {"source": "atdd-author"}


def _seed(root: Path) -> str:
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=root))
    try:
        item = create_work_item(
            conn, "live-preservation-item", state="PLANNED",
            data={"title": "live preservation item", "external_refs": dict(_BOT_REFS), **_LOCAL},
            github_number=_ISSUE_NUMBER,
        )
        StateStore(conn).external_refs.link(
            item.uid, _GITHUB, _ISSUE, str(_ISSUE_NUMBER), data=dict(_PROVENANCE),
        )
        return item.uid
    finally:
        conn.close()


def test_a_live_ingest_destroys_no_locally_held_state(tmp_path) -> None:
    """Stripped keys, unsourced refs and ref provenance all survive the shipped round trip."""
    root = make_checkout(tmp_path / "checkout")
    uid = _seed(root)
    out = root / ".atdd" / "state" / "projection"

    assert atdd_state(root, "project", "--out", str(out)).returncode == 0
    result = atdd_state(root, "hydrate", "--from", str(out))
    assert result.returncode == 0, f"atdd state hydrate failed:\n{result.stderr}"

    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        stored = store.objects.get(uid)
        assert stored is not None, "the object must survive the shipped ingest"
        data = stored.data

        lost = {k: v for k, v in _LOCAL.items() if data.get(k) != v}
        assert not lost, (
            f"the shipped ingest deleted machine-local state it never spoke about: {lost}. "
            "The pre-commit registration gate reads data['branch'] and the "
            "smoke-obligation gate reads data['feature']"
        )

        refs = dict(data.get("external_refs") or {})
        assert (refs.get(_GITHUB) or {}).get(_PR) == "2028", (
            f"github.pr did not survive — the merge must be at the (provider, ref_kind) "
            f"leaf, not the provider. Got {refs!r}"
        )
        assert (refs.get("jira") or {}).get("ticket") == "ATDD-17", f"jira.ticket lost: {refs!r}"
        assert (refs.get(_GITHUB) or {}).get(_ISSUE) == str(_ISSUE_NUMBER), (
            f"the table's own slice is missing after the round trip: {refs!r}"
        )

        row = conn.execute(
            "SELECT data FROM external_refs WHERE provider=? AND ref_kind=? AND ref_value=?",
            (_GITHUB, _ISSUE, str(_ISSUE_NUMBER)),
        ).fetchone()
        assert row is not None, "the ref row itself must survive the ingest"
        assert json.loads(row[0]) == _PROVENANCE, (
            "the ref row's provenance blob was wiped by the restore — link() is "
            f"DO UPDATE SET data=excluded.data. Got {row[0]!r}"
        )
    finally:
        conn.close()
