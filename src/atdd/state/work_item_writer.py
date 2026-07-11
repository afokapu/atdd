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

from atdd.state.identity import assert_uid, assert_uid_immutable, mint_uid
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.projection import STATE_ACTIVE
from atdd.state.store import Object, StateStore

#: ``external_refs.ref_kind`` for the GitHub issue projection (mirrors #1183).
ISSUE_REF_KIND = "issue"

#: The phase a freshly minted work item starts in.
INITIAL_PHASE = "INIT"


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


# --------------------------------------------------------------------------- #
# Projection-native writes (#1400 project-shared-state) — identity is the uid
# --------------------------------------------------------------------------- #
def mint_work_item(
    conn: sqlite3.Connection,
    *,
    slug: str,
    owner_actor: str,
    title: Optional[str] = None,
    body: Optional[str] = None,
    phase: str = INITIAL_PHASE,
) -> Object:
    """Create a work item under a freshly minted, immutable uid (E004).

    Unlike :func:`create_work_item` — which keys the object by its slug, the
    pre-projection identity — this mints a ``wi_<ULID>`` uid that alone names the
    object and its projection file. Slug and title ride along as *display*
    metadata inside ``data`` and may be renamed freely (Y001) without moving
    identity. Two creates carrying the same slug therefore yield two distinct
    objects; a slug is a label, never a key.
    """
    store = StateStore(conn)
    data: Dict[str, Any] = {"slug": slug, "owner_actor": owner_actor, "state": STATE_ACTIVE}
    if title is not None:
        data["title"] = title
    if body is not None:
        data["body"] = body
    return store.objects.upsert(mint_uid(), WORK_ITEM_KIND, state=phase, data=data)


def update_work_item(
    conn: sqlite3.Connection,
    uid: str,
    fields: Dict[str, Any],
) -> Object:
    """Merge ``fields`` into the work item at ``uid``; refuse any uid rewrite.

    The uid is immutable (spec §7.1): a ``fields`` bag carrying a *different*
    ``uid`` raises :class:`~atdd.state.identity.UidImmutableError` and the stored
    object is left exactly as it was. Restating the same uid is allowed — the
    guard stops identity from moving, not from being repeated.
    """
    assert_uid(uid)
    store = StateStore(conn)
    existing = store.objects.get(uid)
    if existing is None:
        raise KeyError(f"work item not found: {uid}")
    assert_uid_immutable(uid, fields.get("uid"))
    merged = {**existing.data, **{k: v for k, v in fields.items() if k != "uid"}}
    phase = merged.pop("phase", existing.state)
    return store.objects.upsert(uid, WORK_ITEM_KIND, state=phase, data=merged)


def rename_work_item(
    conn: sqlite3.Connection,
    uid: str,
    *,
    slug: Optional[str] = None,
    title: Optional[str] = None,
) -> Object:
    """Rename the *display* metadata of a work item (Y001).

    Slug and title are display metadata only: the uid does not change, the
    projection filename does not move, no second file appears, and nothing is
    deleted. Only the fields inside the existing ``<uid>.yaml`` change — which is
    exactly why the projection digest moves while the filename does not.
    """
    fields: Dict[str, Any] = {}
    if slug is not None:
        fields["slug"] = slug
    if title is not None:
        fields["title"] = title
    return update_work_item(conn, uid, fields)
