# URN: test:migrate-projection-authority:migrate-store-projection:E003-SMOKE-001-projection-carries-github-identity
# Acceptance: acc:migrate-projection-authority:E003-SMOKE-001-projection-carries-github-identity
# WMBT: wmbt:migrate-projection-authority:E003
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end through the real `atdd state project` CLI against a real checkout and a real .atdd/state/state.sqlite — the committed YAML on disk names the GitHub issue, and hydrating it back through the real CLI resolves that issue to its uid. Refs #2025.
"""The committed bytes name the issue (E003-SMOKE-001).

wagon: migrate-projection-authority | feature: migrate-store-projection | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:E003

The unit acceptances call `build_documents` and `hydrate` in-process. This one drives the
shipped verbs — `atdd state project` and `atdd state hydrate` — by subprocess against a real
git checkout and a real SQLite file, and READS THE FILE ON DISK rather than believing the
command's stdout. Several commands in this repo report success while writing nothing; the
assertion is the bytes, never the report.

That matters here specifically because the whole point of this issue is what a GitHub
reconciliation workflow will find when it reads the committed projection. That workflow
gets the file, not the return value.

HERMETIC: `--root`, `HOME` and `PYTHONPATH` are pinned inside `tmp_path`, so the developer's
shared Control Root store — which other worktrees are writing to right now — is never
opened. No provider is registered and no GitHub remote exists, which is the point: the
identity comes from the local refs table, never from an API call (I7).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ._live import atdd_state, make_checkout

pytestmark = [pytest.mark.platform]

_GITHUB, _ISSUE = "github", "issue"
_SEED = (("live-projection-item", "PLANNED", 9101), ("second-live-item", "RED", 9102))


def _seed_store(root: Path) -> dict[str, int]:
    """Write a real store through the real production writer; return uid -> issue."""
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=root))
    try:
        bound = {}
        for slug, phase, issue in _SEED:
            item = create_work_item(
                conn, slug, state=phase, data={"title": slug.replace("-", " ")},
                github_number=issue,
            )
            bound[item.uid] = issue
        return bound
    finally:
        conn.close()


def test_the_committed_projection_names_its_github_issue(tmp_path) -> None:
    """The YAML on disk carries the issue, and the shipped hydrate restores it."""
    root = make_checkout(tmp_path / "checkout")
    bound = _seed_store(root)
    out = root / ".atdd" / "state" / "projection"

    result = atdd_state(root, "project", "--out", str(out))
    assert result.returncode == 0, f"atdd state project failed:\n{result.stderr}"

    for uid, issue in bound.items():
        path = out / f"{uid}.yaml"
        assert path.is_file(), f"no projection file for {uid}; wrote {sorted(p.name for p in out.glob('*.yaml'))}"
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        refs = document.get("external_refs") or {}
        assert refs.get(_GITHUB, {}).get(_ISSUE) == str(issue), (
            f"the committed bytes for {uid} do not name issue {issue}. A GitHub "
            "reconciliation workflow reads this file and nothing else, so it has no way "
            f"to know which issue this document is. Got external_refs = {refs!r}"
        )

    # And the inbound half, through the shipped verb, into a store that has been emptied.
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=root))
    try:
        conn.execute("DELETE FROM external_refs")
        conn.commit()
    finally:
        conn.close()

    result = atdd_state(root, "hydrate", "--from", str(out))
    assert result.returncode == 0, f"atdd state hydrate failed:\n{result.stderr}"

    conn = connect(init_state_store(start=root))
    try:
        store = StateStore(conn)
        for uid, issue in bound.items():
            ref = store.external_refs.resolve(_GITHUB, _ISSUE, str(issue))
            assert ref is not None and ref.object_uid == uid, (
                f"after the shipped hydrate, issue {issue} does not resolve to {uid} — "
                "a peer rebuilding shared state from the committed projection cannot "
                "answer 'which work item is issue N?'"
            )
    finally:
        conn.close()
