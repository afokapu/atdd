"""Store-side work-item create/register writer (#1272).

The store-first CREATE — upsert the ``work_item`` object keyed by its slug and
(optionally) link its GitHub issue ``external_ref`` — factored out of
``coach/commands/issue.py`` (#1203 Phase 2) so BOTH archetypes reach it through
``atdd.state`` WITHOUT crossing the planner/coach boundary:

- coach ``atdd issue`` (already has a github number when it registers) and
- planner ``atdd author issue`` (#1272, publishes store-first by default)

both call :func:`create_work_item`. The store is authoritative; the github ref
is one-per-issue (#1220 — the ``external_refs`` unique key enforces it).

Preserves an existing object's lifecycle ``state`` and merges into its ``data``
so a re-registration (idempotent re-author) never clobbers live phase.

Dependency discipline: stdlib + ``atdd.state`` only. This is the foundational
layer both archetypes consume — it MUST NOT import ``atdd.coach`` or
``atdd.planner`` (the reverse of the dependency it exists to serve).
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import Object, StateStore

#: ``external_refs.ref_kind`` for the GitHub issue projection (mirrors #1183).
ISSUE_REF_KIND = "issue"


def create_work_item(
    conn: sqlite3.Connection,
    slug: str,
    *,
    state: Optional[str],
    data: Optional[Dict[str, Any]] = None,
    github_number: Optional[int] = None,
    ref_source: str = "atdd-author",
) -> Object:
    """Create/register a work item store-first; optionally link its github ref.

    Upserts the ``work_item`` keyed by ``slug``. An existing object keeps its
    lifecycle ``state`` (only a brand-new object takes the passed ``state``) and
    has ``data`` merged in, so re-registration is idempotent and never clobbers
    live phase. When ``github_number`` is given, links exactly one github
    ``issue`` external_ref (one-per-issue, #1220); the link's ON CONFLICT keeps a
    single ref, so a re-author with the same number is a no-op update.

    Storage APIs only (no raw SQL). Returns the resulting :class:`Object`.
    Raises on a genuine store failure — the caller owns degrade policy.
    """
    store = StateStore(conn)
    existing = store.objects.get(slug)
    resolved_state = existing.state if existing is not None else state
    merged = {**(existing.data if existing is not None else {}), **(data or {})}
    obj = store.objects.upsert(slug, WORK_ITEM_KIND, state=resolved_state, data=merged)
    if github_number is not None:
        store.external_refs.link(
            slug, GITHUB_PROVIDER, ISSUE_REF_KIND, str(github_number),
            data={"source": ref_source},
        )
        obj = store.objects.get(slug) or obj
    return obj


def revise_work_item_issue(
    conn: sqlite3.Connection,
    issue_number: int,
    *,
    body: Optional[str] = None,
    issue_type: Optional[str] = None,
) -> Object:
    """Revise an existing issue-backed work item through the State Store.

    Resolves the GitHub issue number through ``external_refs`` to the canonical
    work-item uid, merges the requested issue fields into the object's JSON data,
    and preserves the existing lifecycle state. This is the authoritative update;
    provider projection is a caller concern.
    """
    store = StateStore(conn)
    ref = store.external_refs.resolve(
        GITHUB_PROVIDER, ISSUE_REF_KIND, str(issue_number)
    )
    if ref is None:
        raise KeyError(f"github issue #{issue_number} is not registered in the State Store")

    existing = store.objects.get(ref.object_uid)
    if existing is None:
        raise KeyError(
            f"work_item {ref.object_uid!r} for github issue #{issue_number} is missing"
        )
    if existing.kind != WORK_ITEM_KIND:
        raise ValueError(
            f"object {existing.uid!r} is kind {existing.kind!r}, not {WORK_ITEM_KIND!r}"
        )

    updates: Dict[str, Any] = {}
    if body is not None:
        updates["body"] = body
    if issue_type is not None:
        updates["type"] = issue_type
    if not updates:
        raise ValueError("revision requires body and/or issue_type")

    obj = store.objects.upsert(
        existing.uid,
        WORK_ITEM_KIND,
        state=existing.state,
        data={**existing.data, **updates},
    )
    store.events.append(
        "issue_revised",
        object_uid=existing.uid,
        payload={
            "issue_number": issue_number,
            "fields": sorted(updates),
        },
    )
    return obj
