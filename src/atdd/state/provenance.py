"""Authoring provenance for store objects (#1557, child 12 of #1543).

The invariant this module exists to make checkable:

    Every ``work_item`` in the store has a sanctioned authoring event as its
    FIRST event.

**Why provenance rather than interception.** You cannot agent-agnostically
*block* a command — interception is per-agent by construction (a Claude
``PreToolUse`` hook says nothing about Gemini, GLM, or a human at a terminal).
You *can* agnostically detect the artifact the command produces. Provenance is a
property of the record, so it holds for every agent and for no agent at all.

**Why the ``events`` table and not ``objects.data``.** ``events`` is append-only
with a monotonic ``seq``. A provenance fact recorded as an event cannot be
quietly rewritten the way a JSON field on the object could — and "first by
``seq``" is a question only an ordered log can answer.

**Allowlist, never blocklist.** :data:`SANCTIONED_AUTHORING_EVENTS` enumerates
the sanctioned paths. A blocklist would enumerate the forbidden ones and
silently admit the next path nobody thought of; an allowlist admits nothing it
was not told about. :data:`RECONCILED` is deliberately *outside* the allowlist —
see below.

**The inversion.** ``atdd coach reconcile`` used to launder out-of-band creates:
it backfilled them into the store as records indistinguishable from sanctioned
ones. Under this module it stamps :data:`RECONCILED` instead, which is not
sanctioned — so the repair tool becomes the *detector*. A violation can no
longer be washed away by running the repair tool, because the repair tool is
what records it.

**The vocabulary is designed once, for all three creates.** Issue-create is
enforced first, but ``pr create`` and branch creation share the provenance
argument exactly, so their event types are named here rather than invented
piecemeal later (#1557 decision 6).

Dependency discipline: stdlib + ``atdd.state`` only. Nothing here imports,
discovers or consults a provider (I7) — provenance is answered from ``objects``
and ``events`` alone.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from atdd.state.manifest_import import WORK_ITEM_KIND
from atdd.state.store import StateStore

# --------------------------------------------------------------------------- #
# The vocabulary (#1557 decision 6) — designed once for all three creates
# --------------------------------------------------------------------------- #
#: A work item was originated through a sanctioned authoring command
#: (``atdd author issue``). ENFORCED today.
WORK_ITEM_AUTHORED = "work_item_authored"

#: A pull request was originated through ``atdd pr <N>``. Vocabulary only —
#: no validator binds it yet; it is named here so the third create does not
#: invent a competing spelling later.
PULL_REQUEST_AUTHORED = "pull_request_authored"

#: A branch/worktree was originated through ``atdd worktree create <N>``.
#: Vocabulary only, as above.
BRANCH_AUTHORED = "branch_authored"

#: The object was NOT originated locally: ``atdd coach reconcile`` discovered it
#: already existing out-of-band and backfilled it. Deliberately absent from
#: :data:`SANCTIONED_AUTHORING_EVENTS` — this stamp is the detection, not an
#: absolution.
RECONCILED = "work_item_reconciled"

#: The allowlist. Membership here is what makes a first event sanctioned.
#: Adding a name to this set is a deliberate act of granting authority.
SANCTIONED_AUTHORING_EVENTS = frozenset(
    {WORK_ITEM_AUTHORED, PULL_REQUEST_AUTHORED, BRANCH_AUTHORED}
)

#: Every provenance event type this module knows how to write.
PROVENANCE_EVENTS = frozenset(SANCTIONED_AUTHORING_EVENTS | {RECONCILED})

#: ``payload`` key naming the command that originated the record. Free text for
#: the operator; never parsed for a decision.
COMMAND_KEY = "command"

#: Finding clauses (stable strings — a report consumer may switch on these).
CLAUSE_NO_EVENTS = "no_provenance_event"
CLAUSE_UNSANCTIONED_FIRST = "unsanctioned_first_event"
CLAUSE_RECONCILED = "reconciled_provenance"


class ProvenanceStoreUnreadable(Exception):
    """The store could not be read, so provenance could not be evaluated.

    This is NOT a violation — it is the *inability to look*. It is raised rather
    than returned so that no disposition tier can downgrade it to a pass: a
    caller that cannot read the store must fail its run (fail closed), whereas a
    caller that reads the store and finds a violation is subject to the rule's
    declared disposition like any other finding.
    """


@dataclass(frozen=True)
class ProvenanceFinding:
    """One object whose first event is not a sanctioned authoring event."""

    uid: str
    clause: str
    detail: str

    def render(self) -> str:
        return f"{self.uid} [{self.clause}] — {self.detail}"


# --------------------------------------------------------------------------- #
# Writers — the sanctioned stamps
# --------------------------------------------------------------------------- #
def record_authored(
    store: StateStore,
    uid: str,
    *,
    command: str,
    event_type: str = WORK_ITEM_AUTHORED,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Stamp ``uid`` as originated through a sanctioned authoring command.

    Idempotent per object: re-authoring an existing work item (the store-first
    create is an upsert) must not append a second authoring event, or "first
    event" stops meaning anything. Refuses an ``event_type`` outside the
    allowlist — a sanctioned stamp is not something a call site may invent.
    """
    if event_type not in SANCTIONED_AUTHORING_EVENTS:
        raise ValueError(
            f"{event_type!r} is not a sanctioned authoring event; "
            f"expected one of {sorted(SANCTIONED_AUTHORING_EVENTS)}"
        )
    if _has_provenance(store, uid):
        return
    store.events.append(
        event_type, object_uid=uid, payload={COMMAND_KEY: command, **(payload or {})}
    )


def record_reconciled(
    store: StateStore,
    uid: str,
    *,
    discovered_via: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Stamp ``uid`` as backfilled by repair, not originated locally.

    ``discovered_via`` names the repair path in provider-neutral terms (e.g.
    ``"atdd coach reconcile"``) — core records *that* it was reconciled, never
    interrogates a provider about it.

    Idempotent for the same reason :func:`record_authored` is, and for a second
    reason: a record that already carries sanctioned provenance must not be
    re-stamped as reconciled by a later repair run. Repair adds evidence where
    there was none; it never overwrites a good first event.
    """
    if _has_provenance(store, uid):
        return
    store.events.append(
        RECONCILED,
        object_uid=uid,
        payload={"discovered_via": discovered_via, **(payload or {})},
    )


def _has_provenance(store: StateStore, uid: str) -> bool:
    return any(e.event_type in PROVENANCE_EVENTS for e in store.events.list(object_uid=uid))


# --------------------------------------------------------------------------- #
# Reader — the detector
# --------------------------------------------------------------------------- #
def audit_work_items(conn: sqlite3.Connection) -> List[ProvenanceFinding]:
    """Every ``work_item`` whose first event is not a sanctioned authoring event.

    Reads ``objects`` + ``events`` only: no provider call, no provider import,
    no network. Ordered by ``uid`` so a report is stable between runs.

    Raises :class:`ProvenanceStoreUnreadable` when the store cannot be queried.
    An empty store is not unreadable — it legitimately has nothing to say.
    """
    try:
        store = StateStore(conn)
        work_items = store.objects.list(kind=WORK_ITEM_KIND)
    except Exception as exc:  # noqa: BLE001 — any read failure is fail-closed
        raise ProvenanceStoreUnreadable(
            f"State Store could not be read for provenance audit: {exc}"
        ) from exc

    findings: List[ProvenanceFinding] = []
    for obj in work_items:
        try:
            events = store.events.list(object_uid=obj.uid)
        except Exception as exc:  # noqa: BLE001
            raise ProvenanceStoreUnreadable(
                f"event log unreadable for work_item {obj.uid!r}: {exc}"
            ) from exc

        if not events:
            findings.append(
                ProvenanceFinding(
                    uid=obj.uid,
                    clause=CLAUSE_NO_EVENTS,
                    detail=(
                        "work_item has no events at all — it was created outside "
                        "every sanctioned authoring command"
                    ),
                )
            )
            continue

        first = events[0]
        if first.event_type in SANCTIONED_AUTHORING_EVENTS:
            continue
        if first.event_type == RECONCILED:
            findings.append(
                ProvenanceFinding(
                    uid=obj.uid,
                    clause=CLAUSE_RECONCILED,
                    detail=(
                        "work_item carries reconciled provenance: it was backfilled by "
                        f"repair ({first.payload.get('discovered_via', 'unknown path')}), "
                        "not originated through a sanctioned authoring command"
                    ),
                )
            )
            continue
        findings.append(
            ProvenanceFinding(
                uid=obj.uid,
                clause=CLAUSE_UNSANCTIONED_FIRST,
                detail=(
                    f"first event is {first.event_type!r}, which is not a sanctioned "
                    f"authoring event ({sorted(SANCTIONED_AUTHORING_EVENTS)})"
                ),
            )
        )
    return findings
