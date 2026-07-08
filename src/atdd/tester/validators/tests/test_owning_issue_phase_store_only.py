# URN: test:govern-lifecycle:acceptance-walker:owning-issue-phase-store-only
# Issue: #1355 (#1270 slice E — migrate manifest-only readers to the store)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice E — ``owning_issue_phase`` reads the State Store ONLY.

The phase-aware validator binding (#1242) reads an acceptance's owning-issue
phase to exempt pre-test harness acceptances. That read was manifest-only; slice
E repoints it at the State Store (authoritative since #1203), which additionally
carries issues created **store-first** — invisible to the old manifest read.

Discriminators (fail on the old manifest-only implementation):
  - store-first visible: a store work item with NO manifest resolves its phase
    (old code returned ``None`` — no manifest session).
  - store wins over a divergent manifest for the same wagon (non-empty store ⇒
    no auto-import; old code returned the manifest phase).
  - fail-closed preserved: empty store + no manifest ⇒ ``None`` (require test).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.tester.validators._acceptance_walker import RawAcceptance, owning_issue_phase


def _seed_store(root: Path, *, slug: str, issue_number: int, wagon: str, status: str) -> None:
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    marker = root / ".atdd" / "config.yaml"
    if not marker.exists():
        marker.write_text("version: '1.0'\n", encoding="utf-8")  # Control Root marker
    db = init_state_store(start=root)
    conn = connect(db)
    try:
        store = StateStore(conn)
        store.objects.upsert(slug, WORK_ITEM_KIND, state=status,
                             data={"wagon": wagon})
        store.external_refs.link(slug, GITHUB_PROVIDER, "issue", str(issue_number), data={})
    finally:
        conn.close()


def _write_manifest(root: Path, *, wagon: str, status: str) -> None:
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "manifest.yaml").write_text(
        yaml.safe_dump({"version": "2.0", "sessions": [
            {"issue_number": 999, "slug": "m", "wagon": wagon, "status": status}
        ]}),
        encoding="utf-8",
    )


def _acc(repo_root: Path, wagon: str) -> RawAcceptance:
    return RawAcceptance(
        file=repo_root / "plan" / wagon / "D001.yaml",
        kind="wmbt",
        index=0,
        body={"identity": {"urn": f"acc:{wagon}:D001-UNIT-001-x"}},
        location=f"plan/{wagon}/D001.yaml:acceptances[0]",
    )


def test_owning_issue_phase_visible_store_first_without_manifest(tmp_path):
    """Slice E — a store-first work item (no manifest) resolves its phase.

    Old (manifest-only) returned ``None`` because the manifest never tracked it.
    """
    _seed_store(tmp_path, slug="a", issue_number=42, wagon="demo-wagon", status="GREEN")
    assert owning_issue_phase(tmp_path, _acc(tmp_path, "demo-wagon")) == "GREEN"


def test_owning_issue_phase_store_wins_over_divergent_manifest(tmp_path):
    """Slice E — the store phase wins; the divergent manifest is ignored.

    The store is non-empty (holds the wagon item) so no auto-import runs; old
    (fallback) behaviour returned the manifest's ``INIT``.
    """
    _seed_store(tmp_path, slug="a", issue_number=42, wagon="demo-wagon", status="RED")
    _write_manifest(tmp_path, wagon="demo-wagon", status="INIT")
    assert owning_issue_phase(tmp_path, _acc(tmp_path, "demo-wagon")) == "RED"


def test_owning_issue_phase_fail_closed_empty_store_no_manifest(tmp_path):
    """Slice E — no store item + no manifest ⇒ None (fail-closed, unchanged)."""
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    assert owning_issue_phase(tmp_path, _acc(tmp_path, "demo-wagon")) is None
