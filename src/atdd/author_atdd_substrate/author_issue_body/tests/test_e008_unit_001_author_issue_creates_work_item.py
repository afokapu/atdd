# URN: test:author-atdd-substrate:author-issue-body:E008-UNIT-001-author-issue-creates-work-item
# Acceptance: acc:author-atdd-substrate:E008-UNIT-001-author-issue-creates-work-item
# WMBT: wmbt:author-atdd-substrate:E008
# Phase: RED
# Layer: application
"""E008-UNIT-001 — `atdd author issue` creates a work_item in the State Store.

Store-first, by default: the generate path writes a ``work_item`` object under a
freshly minted uid, with state = the Metadata Status and data carrying the
authored fields plus the body. Today the generate path only prints a body string
and writes nothing — so this fails until the store-publish path lands (GREEN).

The object used to be keyed by its slug. It is not any more (#1622): the
projection contract requires a ``wi_<ULID>`` identity and an ``owner_actor``, and
a slug-keyed object is refused on both counts — which is why no projection could
be produced from a store this command filled.
"""
from __future__ import annotations

from atdd.state.identity import is_uid

from ._publish_helpers import open_store, run_author_issue, stub_github_create, work_item


def test_e008_unit_001_author_issue_creates_work_item(tmp_path, monkeypatch):
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    stub_github_create(monkeypatch)  # hermetic: no real gh call

    code, _out = run_author_issue([
        "--title", "Store publish probe",
        "--slug", "e008-store-probe",
        "--type", "implementation",
        "--status", "INIT",
        "--branch", "feat/e008-store-probe",
        "--train", "0003-author-substrate",
        "--feature", "feature:author-atdd-substrate:author-issue-body",
    ])
    assert code == 0, f"author issue should publish and exit 0, got {code}"

    store, conn = open_store(tmp_path)
    try:
        obj = work_item(store, "e008-store-probe")
    finally:
        conn.close()

    assert obj is not None, "no work_item was written to the store (store-first publish missing)"
    assert obj.kind == "work_item"
    # Identity is the minted uid, never the slug (#1622) — the contract requires
    # ^wi_<26-char ULID>$ and an owner_actor, and refuses the object without both.
    assert is_uid(obj.uid), f"identity must be minted, got {obj.uid!r}"
    assert obj.data.get("slug") == "e008-store-probe", "the slug rides along as display metadata"
    assert obj.data.get("owner_actor"), "the contract requires an owner_actor"
    assert obj.state == "INIT", f"work_item state should mirror the Metadata Status, got {obj.state!r}"
    assert obj.data.get("title") == "Store publish probe"
    assert obj.data.get("type") == "implementation"
    assert obj.data.get("branch") == "feat/e008-store-probe"
    assert obj.data.get("feature") == "feature:author-atdd-substrate:author-issue-body"
    assert obj.data.get("body"), "the authored body should be stored in the work_item data"
    assert "### Graph Context" in obj.data["body"]
