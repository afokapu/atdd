"""Hub trace alignment over the State Store (#1168 Phase 6, #1185).

The Hub (#1096) does **not** own a separate SQLite schema — its sessions,
adapters, and events are modelled as ordinary State Store primitives:

- a Hub session is an ``objects`` row of kind ``hub_session``;
- a Hub adapter is an ``objects`` row of kind ``hub_adapter``, linked to its
  session by a ``session_uses_adapter`` relationship;
- adapter/session activity is the ``events`` log (keyed by the session uid).

This module adds the Hub-owned **projections**, a portable **trace export**, and
a **promotion policy** (enqueue a trace to the ``outbox`` for outward sync). It
introduces no new core tables — only Hub semantics over Phases 2-3.

Dependency discipline: stdlib only + ``atdd.state`` (foundational layer).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from atdd.state.store import StateStore

KIND_HUB_SESSION = "hub_session"
KIND_HUB_ADAPTER = "hub_adapter"
REL_SESSION_USES_ADAPTER = "session_uses_adapter"
PROMOTE_OPERATION = "promote_trace"


# --------------------------------------------------------------------------- #
# Recorders (thin Hub semantics over the generic stores)
# --------------------------------------------------------------------------- #
def record_session(store: StateStore, uid: str, *, state: Optional[str] = None,
                   data: Optional[Dict[str, Any]] = None) -> None:
    store.objects.upsert(uid, KIND_HUB_SESSION, state=state, data=data)


def record_adapter(store: StateStore, session_uid: str, adapter_uid: str, *,
                   state: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
    store.objects.upsert(adapter_uid, KIND_HUB_ADAPTER, state=state, data=data)
    store.relationships.add(session_uid, adapter_uid, REL_SESSION_USES_ADAPTER)


def record_event(store: StateStore, session_uid: str, event_type: str, *,
                 payload: Optional[Dict[str, Any]] = None) -> None:
    store.events.append(event_type, object_uid=session_uid, payload=payload)


# --------------------------------------------------------------------------- #
# Projections
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HubSessionRow:
    uid: str
    state: Optional[str]
    data: Dict[str, Any] = field(default_factory=dict)
    adapters: List[str] = field(default_factory=list)
    event_count: int = 0


@dataclass(frozen=True)
class HubAdapterRow:
    uid: str
    state: Optional[str]
    data: Dict[str, Any] = field(default_factory=dict)
    session_uid: Optional[str] = None


def hub_session_projection(store: StateStore) -> List[HubSessionRow]:
    """Every Hub session with its adapters and event count (bulk, no N+1)."""
    rels = store.relationships.list(rel_type=REL_SESSION_USES_ADAPTER)
    adapters_by_session: Dict[str, List[str]] = {}
    for r in rels:
        adapters_by_session.setdefault(r.src_uid, []).append(r.dst_uid)

    counts: Dict[str, int] = {}
    for ev in store.events.list():
        if ev.object_uid is not None:
            counts[ev.object_uid] = counts.get(ev.object_uid, 0) + 1

    return [
        HubSessionRow(
            uid=o.uid,
            state=o.state,
            data=o.data,
            adapters=sorted(adapters_by_session.get(o.uid, [])),
            event_count=counts.get(o.uid, 0),
        )
        for o in store.objects.list(kind=KIND_HUB_SESSION)
    ]


def hub_adapter_projection(store: StateStore) -> List[HubAdapterRow]:
    """Every Hub adapter with the session that owns it (bulk, no N+1)."""
    session_of: Dict[str, str] = {}
    for r in store.relationships.list(rel_type=REL_SESSION_USES_ADAPTER):
        session_of[r.dst_uid] = r.src_uid
    return [
        HubAdapterRow(uid=o.uid, state=o.state, data=o.data, session_uid=session_of.get(o.uid))
        for o in store.objects.list(kind=KIND_HUB_ADAPTER)
    ]


# --------------------------------------------------------------------------- #
# Trace export + promotion
# --------------------------------------------------------------------------- #
def export_trace(store: StateStore, session_uid: str) -> Dict[str, Any]:
    """Assemble a portable trace for one Hub session: session + adapters + events.

    Raises ``KeyError`` if the session does not exist.
    """
    session = store.objects.get(session_uid)
    if session is None or session.kind != KIND_HUB_SESSION:
        raise KeyError(f"hub session not found: {session_uid}")

    adapter_uids = [
        r.dst_uid
        for r in store.relationships.list(src_uid=session_uid, rel_type=REL_SESSION_USES_ADAPTER)
    ]
    adapters = [a for a in (store.objects.get(u) for u in adapter_uids) if a is not None]
    events = store.events.list(object_uid=session_uid)

    return {
        "session": {"uid": session.uid, "state": session.state, "data": session.data},
        "adapters": [{"uid": a.uid, "state": a.state, "data": a.data} for a in adapters],
        "events": [{"seq": e.seq, "type": e.event_type, "payload": e.payload} for e in events],
    }


def promote_trace(store: StateStore, session_uid: str, *, provider: str = "github") -> int:
    """Promotion policy: enqueue the session's trace to the ``outbox`` for outward
    sync and mark the session promoted. Returns the new outbox id.

    Raises ``KeyError`` if the session does not exist.
    """
    trace = export_trace(store, session_uid)  # raises KeyError if missing
    outbox_id = store.sync.enqueue_outbox(provider, PROMOTE_OPERATION, trace)
    session = store.objects.get(session_uid)
    promoted_data = {**session.data, "promoted": True, "promoted_outbox_id": outbox_id}
    store.objects.upsert(session_uid, KIND_HUB_SESSION, state=session.state, data=promoted_data)
    return outbox_id
