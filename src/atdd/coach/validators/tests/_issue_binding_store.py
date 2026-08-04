"""The store-side fixture primitives the issue-binding harnesses share (#1590).

``_bind_issue_feature_helpers`` (#1635) and ``_bind_issue_train_helpers`` (#1590)
each need a real control root, a real State Store, a work item linked to a GitHub
issue number, and a read-back of its ``data``. Written twice, that is what
``coder.refactor.quality-duplication`` reports — and worse, it is a place for the
two harnesses to drift on what "a seeded issue" even means, which would make their
findings incomparable.

Every helper here builds the REAL thing on a tmp path. Nothing is mocked: the
acceptances on both sides are about what actually lands in ``objects.data``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

ISSUE_REF_KIND = "issue"

__all__ = [
    "GITHUB_PROVIDER",
    "ISSUE_REF_KIND",
    "WORK_ITEM_KIND",
    "control_root",
    "link_issue",
    "open_store",
    "read_issue_data",
]


def control_root(tmp_path: Path) -> Path:
    """A directory the State Store will accept as a control root.

    Carries a MINIMAL config: no ``interlocking_layout``, no ``code_roots``, no
    layout keys at all. A fixture that declares atdd's own paths would let a
    resolver pass by finding the toolkit's layout instead of the repo's.
    """
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    return tmp_path


def open_store(root: Path) -> StateStore:
    return StateStore(connect(init_state_store(start=root)))


def link_issue(
    store: StateStore,
    *,
    slug: str,
    issue_number: int,
    state: str,
    data: Dict[str, Any],
) -> str:
    """A work item linked to its github issue, as the real mint leaves it."""
    store.objects.upsert(slug, WORK_ITEM_KIND, state=state, data=data)
    store.external_refs.link(slug, GITHUB_PROVIDER, ISSUE_REF_KIND, str(issue_number))
    return slug


def read_issue_data(store: StateStore, issue_number: int) -> Dict[str, Any]:
    """The stored work item's ``data`` for a github issue number."""
    ref = store.external_refs.resolve(GITHUB_PROVIDER, ISSUE_REF_KIND, str(issue_number))
    assert ref is not None, f"github issue #{issue_number} is not registered in the store"
    obj = store.objects.get(ref.object_uid)
    assert obj is not None, f"work item {ref.object_uid!r} is missing from the store"
    return dict(obj.data or {})


def work_item(store: StateStore, slug: str) -> Optional[Any]:
    """The stored work item by slug, or None — for "a refused mint wrote nothing"."""
    return store.objects.get(slug)
