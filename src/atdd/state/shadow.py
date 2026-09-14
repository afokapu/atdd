"""Shadow-mode projection CI (#1400 migrate-projection-authority, CORE-032, M001).

Between "the projection exists" and "the projection is authority" there is a window, and the
window is where migrations die. Flip the canonicality gate to blocking on day one and the first
unnoticed drift stops every merge in the repo; leave it off and the drift accumulates unseen until
the day you *do* flip it, at which point every branch is red at once and nobody knows which one
broke it.

Shadow mode is the instrument for that window. On every push it recomputes ``project(store)`` and
reports the drift — **and exits zero**. It is a measurement, not a gate.

The exit code is the whole design, and it will read like a bug to anyone who skims it. It is not.
A shadow check that could fail a build is a blocking check with a misleading name; the operator
would have to trust it before they had any evidence it was right, which is precisely the trust the
shadow window exists to *earn*. So: it reports, loudly, in the job summary, and it lets the merge
through. When the drift has been zero for long enough that the team believes it,
``atdd state canonicality`` — which does block — is turned on, and this job's job is done.

It compares against one source, because after the cutover there is one:

``committed``
    ``project(store)`` vs the projection files on disk. Drift here means someone's store and the
    branch's committed projection disagree — the thing the canonicality gate will refuse.

There was a second, ``manifest`` — ``project(store)`` vs the projection the *legacy manifest* would
produce — and it was the only check that could tell you the migration was incomplete rather than
merely stale. It stopped mattering the day the manifest did. ``decommission-manifest`` deleted the
file, so that comparison could only ever report a skip, and a source that is *structurally* skipped
is not a source: it is a heading with nothing under it, in a report whose whole job is to be
believed. Removed in #2023.

**A run that cannot happen still exits zero.** ``project(store)`` is computed before any source is
read, so a store that cannot be projected used to escape as a traceback and exit 1 — through the one
module that declares its exit code a constant precisely so nothing can drift from it. That failure
is now reported as the ``store`` source being unavailable, and the run exits
:data:`SHADOW_EXIT_CODE` like every other. Shadow mode measures; a measurement that dies is a
measurement that says so, not one that gates (#2023).

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state``. No provider (I7).
"""
from __future__ import annotations

import logging
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from atdd.state.projection import (
    PROJECTION_RELATIVE,
    ProjectionError,
    build_documents,
    canonical_bytes,
    MemoryStore,  # re-exported below: a shadow run touches no developer SQLite either
    read_projection,
)
from atdd.state.store import StateStore

_log = logging.getLogger(__name__)

#: What a shadow run compares ``project(store)`` against.
SOURCE_COMMITTED = "committed"
SOURCES: Tuple[str, ...] = (SOURCE_COMMITTED,)

#: Not a comparison source: the name the *store side* is reported under when ``project(store)``
#: itself cannot be computed, so "the run died" is a line in the report rather than a traceback.
SOURCE_STORE = "store"

#: Shadow mode is non-blocking. This is the invariant, stated as a constant so the CLI, the
#: workflow and the tests all read the same number and none of them can drift from it (M001).
SHADOW_EXIT_CODE = 0


@dataclass(frozen=True)
class Drift:
    """One object on which ``project(store)`` and a comparison source disagree."""

    uid: str
    source: str
    #: The fields that differ, each with both sides. Sorted, so the report is deterministic.
    fields: Dict[str, Tuple[Any, Any]] = field(default_factory=dict)
    #: Set when the object is present in one source and absent from the other.
    only_in: Optional[str] = None

    def render(self) -> str:
        if self.only_in is not None:
            return f"{self.uid}: present only in {self.only_in} (vs {self.source})"
        parts = ", ".join(
            f"{name} (store={store!r}, {self.source}={other!r})"
            for name, (store, other) in sorted(self.fields.items())
        )
        return f"{self.uid}: {parts}"


@dataclass(frozen=True)
class ShadowReport:
    """What one shadow run saw. It never fails a build; it only says what it found."""

    drifts: List[Drift] = field(default_factory=list)
    checked: int = 0
    #: Sources that could not be compared at all — reported, not fatal. Carries
    #: :data:`SOURCE_STORE` when ``project(store)`` could not be computed, which is the one failure
    #: that stops the run before any comparison begins.
    unavailable: Dict[str, str] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        """True when nothing drifted. Note this is NOT the exit code — see :data:`SHADOW_EXIT_CODE`."""
        return not self.drifts

    @property
    def exit_code(self) -> int:
        """Always zero. Shadow mode measures; it does not gate (M001)."""
        return SHADOW_EXIT_CODE

    def for_source(self, source: str) -> List[Drift]:
        return [drift for drift in self.drifts if drift.source == source]

    def render(self) -> str:
        lines: List[str] = []
        if SOURCE_STORE in self.unavailable:
            # Never "no drift": nothing was compared, and the two must not read alike.
            lines.append(
                "shadow projection: COULD NOT RUN — project(store) could not be computed, so "
                "nothing was compared"
            )
            lines.append(f"  ({SOURCE_STORE}: {self.unavailable[SOURCE_STORE]})")
            lines.append(
                "shadow mode is NON-BLOCKING and exits 0 by design, including here: this is a "
                "failed measurement, not a failed build. `atdd state canonicality` is the gate."
            )
            return "\n".join(lines)
        if self.clean:
            lines.append(f"shadow projection: no drift ({self.checked} object(s) checked)")
        else:
            lines.append(
                f"shadow projection: {len(self.drifts)} drift(s) across {self.checked} object(s)"
            )
            for source in SOURCES:
                found = self.for_source(source)
                if not found:
                    continue
                lines.append(f"  vs {source} projection ({len(found)}):")
                lines.extend(f"    - {drift.render()}" for drift in found)
        for source, why in sorted(self.unavailable.items()):
            lines.append(f"  ({source} projection unavailable: {why})")
        lines.append(
            "shadow mode is NON-BLOCKING and exits 0 by design: it reports drift while the "
            "cutover is staged. `atdd state canonicality` is the gate that blocks."
        )
        return "\n".join(lines)


def _diff(
    left: Mapping[str, Mapping[str, Any]],
    right: Mapping[str, Mapping[str, Any]],
    source: str,
) -> List[Drift]:
    """Every object on which ``left`` (the store) and ``right`` (a comparison source) disagree."""
    drifts: List[Drift] = []
    for uid in sorted(set(left) | set(right)):
        if uid not in right:
            drifts.append(Drift(uid=uid, source=source, only_in="store"))
            continue
        if uid not in left:
            drifts.append(Drift(uid=uid, source=source, only_in=source))
            continue
        ours, theirs = left[uid], right[uid]
        fields = {
            name: (ours.get(name), theirs.get(name))
            for name in sorted(set(ours) | set(theirs))
            if ours.get(name) != theirs.get(name)
        }
        if fields:
            drifts.append(Drift(uid=uid, source=source, fields=fields))
    return drifts


def compare(
    store: StateStore,
    *,
    root: Path,
    projection_dir: Optional[Path] = None,
    sources: Sequence[str] = SOURCES,
) -> ShadowReport:
    """Recompute ``project(store)`` and report its drift against each source. Never raises to gate.

    Pure measurement: it writes no projection file and mutates no store. The canonical bytes are
    the unit of comparison, exactly as the blocking gate will compare them — so a clean shadow run
    is real evidence that flipping the gate is safe, and not merely a rehearsal of a different check.
    """
    root = Path(root)
    projection_dir = Path(projection_dir) if projection_dir is not None else root / PROJECTION_RELATIVE

    drifts: List[Drift] = []
    unavailable: Dict[str, str] = {}

    try:
        ours = build_documents(store)
    except ProjectionError as exc:
        # The store side is computed before any source is read, so its failure would otherwise
        # escape as a traceback and exit non-zero — out of the one module that declares its exit
        # code a constant so nothing can drift from it. Report it and carry on measuring nothing:
        # an operator must be able to tell "the projection is clean" from "the check never ran".
        _log.warning(
            "shadow could not compute project(store); the run is non-blocking and exits 0 (M001)",
            extra={"root": str(root), "error": str(exc), "exit_code": SHADOW_EXIT_CODE},
        )
        return ShadowReport(unavailable={SOURCE_STORE: str(exc)})

    if SOURCE_COMMITTED in sources:
        committed = read_projection(projection_dir)
        drifts.extend(_diff(ours, committed, SOURCE_COMMITTED))

    report = ShadowReport(drifts=drifts, checked=len(ours), unavailable=unavailable)
    if drifts:
        _log.warning(
            "shadow projection found drift; the run is non-blocking and exits 0 (M001)",
            extra={"root": str(root), "drifts": [d.render() for d in drifts],
                "exit_code": SHADOW_EXIT_CODE},
        )
    return report


def compare_repo(
    root: Path,
    *,
    projection_dir: Optional[Path] = None,
    sources: Sequence[str] = SOURCES,
) -> ShadowReport:
    """:func:`compare`, against the repo's own State Store. Read-only."""
    from atdd.state.db import connect, init_state_store

    root = Path(root)
    conn = connect(init_state_store(start=root))
    try:
        return compare(
            StateStore(conn), root=root, projection_dir=projection_dir, sources=sources,
        )
    finally:
        conn.close()


def canonical_of(store: StateStore) -> Dict[str, bytes]:
    """The canonical bytes ``project(store)`` would write — computed, never written to disk."""
    return {uid: canonical_bytes(doc) for uid, doc in build_documents(store).items()}


__all__ = [
    "Drift", "SHADOW_EXIT_CODE", "SOURCES", "SOURCE_COMMITTED", "SOURCE_STORE", "ShadowReport",
    "MemoryStore", "canonical_of", "compare", "compare_repo",
]
