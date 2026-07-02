# URN: test:govern-lifecycle:issue-graph:store-first-wagon-and-train
# Issue: #1318 (#1270 slice A — decommission the manifest mirror)
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""#1270 slice A — the issue-graph context readers read the State Store first.

``issue_graph`` resolves an issue's wagon and train for the spawn-prompt
architecture context. These reads were manifest-only; #1203 made the store
authoritative. The discriminating tests seed the store and a *divergent*
manifest for the same issue and assert the reader returns the **store** value —
which fails on the old manifest-only implementation and passes once the reader
is store-first. The manifest fallback is retained for an un-imported store.
"""
from __future__ import annotations

import yaml

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore
from atdd.coach.commands.issue_graph import (
    _wagon_slug_for_issue,
    build_issue_architecture_context,
)


def _seed_store(root, *, slug, issue_number, wagon=None, train=None, status="PLANNED"):
    """Register one work item (with optional wagon/train) directly in the store."""
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    marker = root / ".atdd" / "config.yaml"
    if not marker.exists():
        marker.write_text("version: '1.0'\n", encoding="utf-8")  # Control Root marker
    db = init_state_store(start=root)
    conn = connect(db)
    try:
        store = StateStore(conn)
        data = {"issue_number": issue_number}
        if wagon:
            data["wagon"] = wagon
        if train:
            data["train"] = train
        store.objects.upsert(slug, WORK_ITEM_KIND, state=status, data=data)
        store.external_refs.link(
            slug, GITHUB_PROVIDER, "issue", str(issue_number), data={}
        )
    finally:
        conn.close()


def _write_manifest(root, sessions):
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    path = root / ".atdd" / "manifest.yaml"
    path.write_text(yaml.safe_dump({"version": "2.0", "sessions": sessions}), encoding="utf-8")
    return path


def test_wagon_slug_for_issue_prefers_store_over_divergent_manifest(tmp_path):
    """Store wagon wins over a different manifest wagon for the same issue."""
    _seed_store(tmp_path, slug="my-item", issue_number=42, wagon="govern-lifecycle")
    _write_manifest(
        tmp_path,
        [{"issue_number": 42, "slug": "my-item", "wagon": "author-plan-substrate"}],
    )
    assert _wagon_slug_for_issue(42, tmp_path) == "govern-lifecycle"


def test_wagon_slug_for_issue_falls_back_to_manifest(tmp_path):
    """With no store wagon, the manifest mirror still resolves the wagon."""
    # Store holds the issue but no wagon; manifest carries the wagon.
    _seed_store(tmp_path, slug="x", issue_number=7)
    _write_manifest(tmp_path, [{"issue_number": 7, "slug": "x", "wagon": "define-plans"}])
    assert _wagon_slug_for_issue(7, tmp_path) == "define-plans"


def test_build_architecture_context_uses_store_train(tmp_path, monkeypatch):
    """The architecture-context train is read store-first over a divergent manifest."""
    captured = {}

    def _fake_ctx_for_wagon(wagon_slug, *, train_id=None, repo_root=None):
        captured["wagon"] = wagon_slug
        captured["train"] = train_id
        return "## Architecture context\n"

    monkeypatch.setattr(
        "atdd.coach.commands.issue_graph.build_architecture_context_for_wagon",
        _fake_ctx_for_wagon,
    )
    _seed_store(
        tmp_path, slug="ctx-item", issue_number=55,
        wagon="govern-lifecycle", train="0002-coach-drives-lifecycle",
    )
    _write_manifest(
        tmp_path,
        [{"issue_number": 55, "slug": "ctx-item", "wagon": "govern-lifecycle",
          "train": "0001-self-compliance-validate"}],
    )
    build_issue_architecture_context(55, repo_root=tmp_path)
    assert captured["train"] == "0002-coach-drives-lifecycle"  # store, not manifest
