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

from atdd.state.body_heading import has_h1, retitle_h1
from atdd.state.identity import assert_uid_immutable, mint_uid
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.projection import STATE_ACTIVE
from atdd.state.store import Object, StateStore

#: ``external_refs.ref_kind`` for the GitHub issue projection (mirrors #1183).
ISSUE_REF_KIND = "issue"

#: The phase a freshly minted work item starts in.
INITIAL_PHASE = "INIT"

#: The data key carrying a work item's *display* slug — its pre-projection identity.
SLUG_KEY = "slug"

#: The owner a work item has when the caller does not name one. A marker, not an
#: invented person: "we do not know who" is a fact worth recording, and the contract
#: requires the field (mirrors ``manifest_migration.UNATTRIBUTED_OWNER``).
UNATTRIBUTED_OWNER = "unattributed"


def resolve_work_item(
    store: StateStore,
    slug: str,
    *,
    github_number: Optional[int] = None,
) -> Optional[Object]:
    """The work item ``slug`` (or ``github_number``) names, or ``None``.

    Identity is the uid, and the uid is a ``wi_<ULID>`` that no caller knows in
    advance — so every path that used to say ``objects.get(slug)`` has to resolve
    instead. The ladder is ordered by how durable each answer is:

    1. **the GitHub issue ref**, when the caller has a number. An issue number
       outlives a rename; the slug does not. Resolving here first is what stops a
       re-registration under a renamed slug from minting a second object for a work
       item that already exists.
    2. **``data.slug``** — the display slug of an already-migrated object.
    3. **the uid itself** — a store that has not been through
       :func:`~atdd.state.manifest_migration.migrate_store` still keys its objects by
       slug, and those rows must stay reachable until it has.

    Step 3 is why this is a ladder and not a single query: during the migration
    window both shapes exist, and a resolver that knew only one of them would report
    a live work item as absent — and its caller would then create it again.
    """
    if github_number is not None:
        ref = store.external_refs.resolve(GITHUB_PROVIDER, ISSUE_REF_KIND, str(github_number))
        if ref is not None:
            found = store.objects.get(ref.object_uid)
            if found is not None and found.kind == WORK_ITEM_KIND:
                return found
    if slug:
        matches = store.objects.find_by_field(WORK_ITEM_KIND, SLUG_KEY, slug)
        if matches:
            return matches[0]
        legacy = store.objects.get(slug)
        if legacy is not None and legacy.kind == WORK_ITEM_KIND:
            return legacy
    return None


def create_work_item(
    conn: sqlite3.Connection,
    slug: str,
    *,
    state: Optional[str],
    data: Optional[Dict[str, Any]] = None,
    github_number: Optional[int] = None,
    ref_source: str = "atdd-author",
    owner_actor: str = UNATTRIBUTED_OWNER,
) -> Object:
    """Create/register a work item store-first; optionally link its github ref.

    Identity is a freshly **minted** ``wi_<ULID>`` uid, and the slug rides inside
    ``data`` as display metadata (spec §10 rule 1). This is the whole of #1622: this
    function is the path every production caller uses, it used to key the object by
    its slug, and an object so keyed is one the projection contract refuses — on its
    uid *and* on its missing ``owner_actor``, both required. A store filled by this
    writer could therefore never be projected at all, so ``atdd state project``
    refused on the first object and wrote nothing.

    Re-registration stays idempotent, and that is the delicate part: the object is
    *resolved* through :func:`resolve_work_item` (github ref → ``data.slug`` → legacy
    uid) rather than fetched by slug. Minting without resolving would mean every
    re-author inserted a second row for a work item that already existed — a
    duplicate corpus, which is worse than the refusal it replaced. An existing object
    keeps its lifecycle ``state`` (only a brand-new object takes the passed ``state``)
    and has ``data`` merged in, so live phase is never clobbered.

    ``owner_actor`` is recorded once, at create, and never overwritten by a later
    re-registration — the field is the *owner*, and a re-author is not a change of
    ownership. When ``github_number`` is given, links exactly one github ``issue``
    external_ref (one-per-issue, #1220); the link's ON CONFLICT keeps a single ref,
    so a re-author with the same number is a no-op update.

    Storage APIs only (no raw SQL). Returns the resulting :class:`Object`.
    Raises on a genuine store failure — the caller owns degrade policy.
    """
    store = StateStore(conn)
    existing = resolve_work_item(store, slug, github_number=github_number)
    uid = existing.uid if existing is not None else mint_uid()
    resolved_state = existing.state if existing is not None else state
    merged: Dict[str, Any] = {
        **(existing.data if existing is not None else {}),
        **(data or {}),
        SLUG_KEY: slug,
    }
    merged.setdefault("owner_actor", owner_actor)
    merged.setdefault("state", STATE_ACTIVE)
    obj = store.objects.upsert(uid, WORK_ITEM_KIND, state=resolved_state, data=merged)
    if github_number is not None:
        store.external_refs.link(
            uid, GITHUB_PROVIDER, ISSUE_REF_KIND, str(github_number),
            data={"source": ref_source},
        )
        obj = store.objects.get(uid) or obj
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

    **Identity is resolved by store membership, not by uid shape** (Y002, #1653).
    This used to open with ``assert_uid(uid)``, which required ``wi_<ULID>`` and
    therefore matched **0 of the 822** work items the store actually holds: 633
    are ``unverified:<slug>``, 189 are bare slugs, and the authoring path mints
    the slug *as* the uid (``author_publish.derive_slug``). That gate was never a
    store-wide invariant — :func:`revise_work_item_issue` writes to those same
    slug uids today by upserting directly, and does so correctly. It was one
    stray precondition on one lookup path, and it made this function dead code.

    The ``wi_<ULID>`` grammar keeps its real jobs — minting (:func:`mint_uid`),
    the projection document, commit trailers, the provider seam — none of which
    is a *lookup*. A uid the store does not hold raises :class:`KeyError`, which
    is the honest error for a typo and is also correct for every future uid form.

    The lookup therefore goes through :func:`resolve_work_item`, not
    ``objects.get`` (#1622). Once minting moved identity to ``wi_<ULID>`` and put
    the slug in ``data.slug``, a bare ``get`` answered only for callers who
    already held the minted uid — and every caller addressing by slug, which is
    what Y002 guarantees keeps working, got ``work item not found`` on a work item
    the store plainly holds. Writing back under ``existing.uid`` rather than the
    caller's key is the other half: upserting at the slug would mint a SECOND
    object for a work item that already exists.

    The raw ``objects.get`` is kept as a fallback, and is not redundant:
    :func:`resolve_work_item` filters to ``WORK_ITEM_KIND``, so resolving alone
    would make a foreign-kind object simply *absent* and turn the kind refusal
    below into a bare ``KeyError`` — losing the guard Y002-UNIT-002 pins, which
    requires the refusal to name the offending kind.

    The kind check is what the shape gate was incidentally providing: this
    function upserts with ``WORK_ITEM_KIND``, so addressing an ``agent_session``,
    ``release`` or ``hub_adapter`` object would have silently rewritten its kind
    once the shape gate stopped shielding them. It mirrors the guard
    :func:`revise_work_item_issue` already carries.
    """
    store = StateStore(conn)
    existing = resolve_work_item(store, uid) or store.objects.get(uid)
    if existing is None:
        raise KeyError(f"work item not found: {uid}")
    if existing.kind != WORK_ITEM_KIND:
        raise ValueError(
            f"object {existing.uid!r} is kind {existing.kind!r}, not {WORK_ITEM_KIND!r}"
        )
    assert_uid_immutable(existing.uid, fields.get("uid"))
    merged = {**existing.data, **{k: v for k, v in fields.items() if k != "uid"}}
    phase = merged.pop("phase", existing.state)
    return store.objects.upsert(existing.uid, WORK_ITEM_KIND, state=phase, data=merged)


def rename_work_item(
    conn: sqlite3.Connection,
    uid: str,
    *,
    slug: Optional[str] = None,
    title: Optional[str] = None,
) -> Object:
    """Rename the *display* metadata of a work item (Y001, Y002).

    Slug and title are display metadata only: the uid does not change, the
    projection filename does not move, no second file appears, and nothing is
    deleted. Only the fields inside the existing ``<uid>.yaml`` change — which is
    exactly why the projection digest moves while the filename does not.

    A ``title`` rename also rewrites the body's leading H1 **when the body has
    one**, in the same write, because the title and that heading are the same
    fact stored twice — ``atdd author issue --title`` documents itself as "the H1
    + Problem Statement subject". Leaving the H1 stale is precisely the
    divergence #1654 exists to catch, so this verb must not mint it (#1652
    orchestrator ruling).

    It is equally deliberate that a body **without** an H1 is left alone rather
    than given one: 619 of the 822 live bodies carry no leading H1, and
    synthesising headings into them would be a corpus migration wearing a
    rename's clothes. ``slug`` is unaffected either way — a slug is not
    duplicated in the body. See :mod:`atdd.state.body_heading`, the single
    fence-aware parser that #1654 shares rather than re-implements.
    """
    fields: Dict[str, Any] = {}
    if slug is not None:
        fields["slug"] = slug
    if title is not None:
        fields["title"] = title
        existing = resolve_work_item(StateStore(conn), uid)
        body = (existing.data.get("body") if existing is not None else None)
        if has_h1(body):
            fields["body"] = retitle_h1(body, title)
    return update_work_item(conn, uid, fields)


def revise_work_item_issue(
    conn: sqlite3.Connection,
    issue_number: int,
    *,
    body: Optional[str] = None,
    issue_type: Optional[str] = None,
    feature: Optional[str] = None,
    title: Optional[str] = None,
) -> Object:
    """Revise an existing issue-backed work item through the State Store.

    Resolves the GitHub issue number through ``external_refs`` to the canonical
    work-item uid, merges the requested issue fields into the object's JSON data,
    and preserves the existing lifecycle state. This is the authoritative update;
    provider projection is a caller concern.

    ``feature`` completes the revise chain (#1635). It was previously accepted by
    ``atdd author issue --revise`` and dropped here: this function had no
    parameter for it, so the value was discarded between the CLI and the store.
    Measured across eight issues on 2026-07-28 — the body updated on all eight
    and ``data.feature`` stayed NULL on all eight. A revision that names no
    feature leaves an existing binding untouched (``None`` means "unchanged",
    never "clear it").

    ``title`` closes the same gap for the last flag that had it (#1661). It was
    accepted by ``atdd author issue --revise`` and dropped here for the same
    reason: no parameter to carry it. Measured 2026-08-02 — ``--revise --title X
    --type bug`` exited 0 with ``data.title`` unchanged. Where a body accompanied
    it the result was worse than a no-op: the body's H1 moved and the issue title
    did not, so the two disagreed until an operator repaired it by hand (#1636).
    ``None`` means "unchanged" here too.
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
    if feature is not None:
        updates["feature"] = feature
    if title is not None:
        updates["title"] = title
    if not updates:
        raise ValueError("revision requires body, issue_type, feature and/or title")

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
