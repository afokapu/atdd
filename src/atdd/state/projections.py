"""ATDD State Store read-side projections (#1168 Phase 3, #1182).

Projections are typed query models derived from objects/relationships/events/
external_refs — the read side that consumers (a local Kanban view, lifecycle
queries) use instead of touching tables directly. Phase 3 ships the three core
projections; Hub- and provider-owned projections layer on in later phases.

A projection is a pure read: it never writes. Each takes a
:class:`sqlite3.Connection` (or anything with a compatible ``execute``).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from atdd.state.store import EventStore, ExternalRefStore, ObjectStore

#: Canonical object kinds for the core projections.
KIND_WORK_ITEM = "work_item"
KIND_RUN = "run"
KIND_EVIDENCE = "evidence"
#: The singleton release object (#1172) — uid == kind == "release".
KIND_RELEASE = "release"
RELEASE_UID = "release"


@dataclass(frozen=True)
class WorkItemRow:
    """A work item plus its external projections (e.g. the GitHub issue number)."""

    uid: str
    state: Optional[str]
    data: Dict[str, Any] = field(default_factory=dict)
    #: provider -> ref_value, e.g. {"github": "1182"} for the mirrored issue.
    external: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RunRow:
    uid: str
    state: Optional[str]
    data: Dict[str, Any] = field(default_factory=dict)
    event_count: int = 0
    last_event_type: Optional[str] = None


@dataclass(frozen=True)
class EvidenceRow:
    uid: str
    state: Optional[str]
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReleaseRow:
    """The singleton release object: current version + bump history summary (#1172)."""

    version: Optional[str]
    #: count of ``version_bumped`` events recorded against the release object.
    bump_count: int = 0
    #: the most recent bump payload (``{from,to,change_class,pr}``), or ``None``.
    last_bump: Optional[Dict[str, Any]] = None


def work_item_projection(conn: sqlite3.Connection) -> List[WorkItemRow]:
    """Every ``work_item`` object with its external refs folded in (issue numbers etc.).

    Bulk read (two queries total, grouped in Python) — never a per-object query.
    """
    objects = ObjectStore(conn)
    refs = ExternalRefStore(conn)
    by_object: Dict[str, Dict[str, str]] = defaultdict(dict)
    for ref in refs.all():
        by_object[ref.object_uid][ref.provider] = ref.ref_value
    return [
        WorkItemRow(uid=obj.uid, state=obj.state, data=obj.data, external=dict(by_object[obj.uid]))
        for obj in objects.list(kind=KIND_WORK_ITEM)
    ]


def run_projection(conn: sqlite3.Connection) -> List[RunRow]:
    """Every ``run`` object with a small event summary.

    Bulk read (two queries total, grouped in Python) — never a per-object query.
    """
    objects = ObjectStore(conn)
    events = EventStore(conn)
    counts: Dict[str, int] = defaultdict(int)
    last_type: Dict[str, str] = {}
    for ev in events.list():                 # all events, already ordered by seq
        if ev.object_uid is None:
            continue
        counts[ev.object_uid] += 1
        last_type[ev.object_uid] = ev.event_type
    return [
        RunRow(uid=obj.uid, state=obj.state, data=obj.data,
               event_count=counts[obj.uid], last_event_type=last_type.get(obj.uid))
        for obj in objects.list(kind=KIND_RUN)
    ]


def evidence_projection(conn: sqlite3.Connection) -> List[EvidenceRow]:
    """Every ``evidence`` object."""
    objects = ObjectStore(conn)
    return [EvidenceRow(uid=o.uid, state=o.state, data=o.data)
            for o in objects.list(kind=KIND_EVIDENCE)]


VERSION_BUMPED_EVENT = "version_bumped"


def release_projection(conn: sqlite3.Connection) -> Optional[ReleaseRow]:
    """The singleton release object with a small bump-history summary (#1172).

    Returns ``None`` when no ``release`` object exists (a store predating
    migration v2, or one never seeded). Two queries total — the object plus its
    events — never a per-event query.
    """
    obj = ObjectStore(conn).get(RELEASE_UID)
    if obj is None:
        return None
    bumps = [e for e in EventStore(conn).list(object_uid=RELEASE_UID)
             if e.event_type == VERSION_BUMPED_EVENT]
    return ReleaseRow(
        version=obj.data.get("version"),
        bump_count=len(bumps),
        last_bump=bumps[-1].payload if bumps else None,
    )
