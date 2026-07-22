"""The seven local authoring commands (#1400 CORE-011, spec §3).

This is the *only* sanctioned way to change a work item locally. Each function is
one authoring command, and each appends exactly one typed overlay event in the same
transaction as the object write it describes — so the store and the log can never
disagree about what the developer did.

    create_object            → object_created
    update_body              → body_updated
    request_transition       → phase_transition_requested
    update_train             → train_updated
    add_wmbt                 → wmbt_added
    request_tombstone        → tombstone_requested
    apply_external_ref       → external_ref_applied

Why a separate surface from :mod:`atdd.state.work_item_writer`: that module holds
the raw store writers, which *hydrate* and *replay* also use — they write public
state that already exists in the shared truth or in the log, and are not authoring.
Everything a developer *originates* comes through here, and therefore gets logged.

``request_transition`` takes the phase it is moving **from**. That is not
bookkeeping: it is the optimistic-concurrency check that makes same-object
divergence conflict by design (K001). Without it, reconcile could only see "B wants
GREEN" and would have to guess whether B knew A had already moved the object.

Dependency discipline: stdlib + ``atdd.state`` only.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Dict, Optional

from atdd.state import overlay, tombstone
from atdd.state.identity import assert_uid, mint_uid
from atdd.state.overlay import OverlayEvent
from atdd.state.projection import STATE_ACTIVE
from atdd.state.store import StateStore
from atdd.state.work_item_writer import INITIAL_PHASE


def _phase_of(conn: sqlite3.Connection, uid: str) -> Optional[str]:
    obj = StateStore(conn).objects.get(uid)
    return None if obj is None else obj.state


def create_object(
    conn: sqlite3.Connection,
    *,
    slug: str,
    owner_actor: str,
    title: Optional[str] = None,
    body: Optional[str] = None,
    phase: str = INITIAL_PHASE,
    uid: Optional[str] = None,
) -> OverlayEvent:
    """Mint a work item under a fresh immutable uid, logging ``object_created``.

    ``uid`` exists so a test can pin identity; production callers pass none and get
    a freshly minted one. Slug and title are display metadata — they never name the
    object (spec §10 rule 1).
    """
    resolved = mint_uid() if uid is None else assert_uid(uid)
    data: Dict[str, Any] = {"slug": slug, "owner_actor": owner_actor, "state": STATE_ACTIVE}
    if title is not None:
        data["title"] = title
    if body is not None:
        data["body"] = body
    return overlay.author(
        conn, overlay.OBJECT_CREATED, resolved, {"phase": phase, "data": data},
    )


def update_body(conn: sqlite3.Connection, uid: str, body: str) -> OverlayEvent:
    """Rewrite the body, logging ``body_updated``."""
    return overlay.author(conn, overlay.BODY_UPDATED, assert_uid(uid), {"body": body})


def request_transition(
    conn: sqlite3.Connection,
    uid: str,
    to_phase: str,
    *,
    from_phase: Optional[str] = None,
) -> OverlayEvent:
    """Request a phase transition, logging ``phase_transition_requested``.

    Records the phase the object is moving *from* (read from the store when the
    caller does not pass it). Reconcile compares that against the incoming
    projection: if the shared truth has since moved the object somewhere else, the
    two developers diverged on the same object and the replay conflicts rather than
    silently picking the further-along phase (K001).
    """
    uid = assert_uid(uid)
    resolved_from = _phase_of(conn, uid) if from_phase is None else from_phase
    return overlay.author(
        conn,
        overlay.PHASE_TRANSITION_REQUESTED,
        uid,
        {"from_phase": resolved_from, "to_phase": to_phase},
    )


def update_train(conn: sqlite3.Connection, uid: str, train: Optional[str]) -> OverlayEvent:
    """Set (or clear) the train, logging ``train_updated``."""
    return overlay.author(conn, overlay.TRAIN_UPDATED, assert_uid(uid), {"train": train})


def add_wmbt(conn: sqlite3.Connection, uid: str, wmbt: str) -> OverlayEvent:
    """Attach a WMBT, logging ``wmbt_added``. Re-adding an existing one is a no-op."""
    return overlay.author(conn, overlay.WMBT_ADDED, assert_uid(uid), {"wmbt": wmbt})


def request_tombstone(
    conn: sqlite3.Connection,
    uid: str,
    reason: str,
    *,
    actor: Optional[str] = None,
    default_actor: str = "unattributed",
) -> OverlayEvent:
    """Retire an object, logging ``tombstone_requested``.

    A tombstone is a *record*, never a file deletion (spec §10 rule 3): the object
    stays in the projection carrying ``state: TOMBSTONED``, so peers learn it was
    retired instead of watching it silently vanish.

    The record carries a **reason digest** as well as the prose reason — the digest is
    what a merge can compare and what refuses two sides retiring one object for
    different stated reasons (K001).

    It also carries the provenance a committed retirement must be auditable by (#1580),
    and this is the right place to capture it because this is the only place where it is
    still knowable:

    - ``prior_digest`` is taken from the object **as it stands right now**, before the
      retirement is applied. A moment later that state exists nowhere.
    - ``source_generation`` is the store's base commit — the generation of shared truth
      this retirement was decided against.

    Neither can be reconstructed downstream, which is precisely why the incident's audit
    trail could not be reconstructed either. ``actor`` falls back to a marker rather than
    being omitted: "we do not know who" is a fact worth recording, and an absent field
    would instead make the record unreadable at the far end.
    """
    from atdd.state import metadata  # local: authoring is imported by metadata's callers
    from atdd.state.projection import build_document, object_digest

    uid = assert_uid(uid)
    current = StateStore(conn).objects.get(uid)
    prior_digest = object_digest(build_document(current)) if current is not None else None

    return overlay.author(
        conn,
        overlay.TOMBSTONE_REQUESTED,
        uid,
        {
            "tombstone": tombstone.tombstone_record(
                reason,
                actor=actor or default_actor,
                source_generation=metadata.base_commit(conn) or metadata.UNANCHORED_GENERATION,
                prior_digest=prior_digest or object_digest({"uid": uid}),
            )
        },
    )


def apply_external_ref(
    conn: sqlite3.Connection, uid: str, provider: str, ref: str
) -> OverlayEvent:
    """Record a provider's ref, logging ``external_ref_applied``.

    Core *carries* external refs; it never *consults* them for a lifecycle decision
    (I7). This event exists so a ref applied locally survives a reconcile like any
    other local authoring — not so that the provider gains authority over phase.
    """
    return overlay.author(
        conn,
        overlay.EXTERNAL_REF_APPLIED,
        assert_uid(uid),
        {"provider": provider, "ref": ref},
    )
