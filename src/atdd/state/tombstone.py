"""Retirement as a record, never a deletion (#1400 govern-projection-fields, K001).

Spec §10 rule 3: *a tombstone is a record, not a file deletion.* The difference is what a
peer sees. A deleted projection file is indistinguishable, on their side of a merge, from
a file that was never created — so a stale branch reintroduces the object and nobody
notices. A tombstoned file is a *claim*, carried in the shared truth: the object was
retired, here is the reason it was retired for, and any merge that tries to bring the uid
back to life has something concrete to be refused by.

So retirement here:

- writes ``state: TOMBSTONED`` plus ``tombstone`` metadata carrying a **reason digest**
  (the reason itself is prose; the digest is what a trailer and a merge can compare);
- removes no file — :func:`retire` touches the store, and the projector then emits the
  same ``<uid>.yaml`` it always did, carrying the retirement;
- leaves physical removal to exactly one operation, :func:`compact_archive`, which is an
  archival step an operator runs deliberately and never something a merge can do.

:mod:`atdd.state.merge_driver` reads :func:`is_tombstoned` to refuse resurrection.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` only. No provider.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from atdd.state.projection import (
    DIGEST_PREFIX,
    PROJECTION_SUFFIX,
    REQUIRED_TOMBSTONE_FIELDS,
    STATE_TOMBSTONED,
    read_projection,
)

_log = logging.getLogger(__name__)


def reason_digest(reason: str) -> str:
    """The ``sha256:<hex>`` stamp over a retirement reason.

    The reason is prose and may be rewritten in a hundred equivalent ways; the digest is
    the thing two sides of a merge can actually compare, and the thing a commit trailer can
    carry without carrying the prose.
    """
    return DIGEST_PREFIX + hashlib.sha256(reason.encode("utf-8")).hexdigest()


def tombstone_record(
    reason: str,
    *,
    actor: Optional[str] = None,
    source_generation: Optional[str] = None,
    prior_digest: Optional[str] = None,
) -> Dict[str, Any]:
    """The ``tombstone`` metadata a retirement writes onto the object.

    The optional signature is kept because the *local* authoring path legitimately does not
    know some of this yet: an overlay tombstone is authored before it has a generation to
    belong to. What must carry the full provenance is a tombstone that has reached the
    **committed projection**, and that is enforced where it is read
    (:func:`atdd.state.projection.validate_document`), not here.
    """
    record: Dict[str, Any] = {"reason": reason, "reason_digest": reason_digest(reason)}
    if actor:
        record["actor"] = actor
    if source_generation:
        record["source_generation"] = source_generation
    if prior_digest:
        record["prior_digest"] = prior_digest
    return record


def missing_provenance(record: Optional[Mapping[str, Any]]) -> List[str]:
    """The provenance fields a committed tombstone record lacks, in declaration order.

    The field list lives in :mod:`atdd.state.projection` with the rest of the document
    shape — the schema layer owns what a committed document must look like, and this
    module is one of its callers.
    """
    present = record or {}
    return [name for name in REQUIRED_TOMBSTONE_FIELDS if not present.get(name)]


def is_tombstoned(document: Optional[Mapping[str, Any]]) -> bool:
    """Whether a projection document carries a retirement."""
    return bool(document) and document.get("state") == STATE_TOMBSTONED


def retire(conn, uid: str, reason: str, *, actor: Optional[str] = None):
    """Retire an object: ``state: TOMBSTONED`` + a reason digest, and no file goes away (K001).

    Routed through the authoring surface, so the retirement is logged as an overlay event
    like every other local change — a retirement that reconcile could not replay would be a
    retirement a developer silently loses on the next pull.
    """
    from atdd.state import authoring  # local: authoring imports this module for the digest

    return authoring.request_tombstone(conn, uid, reason, actor=actor)


def compact_archive(
    projection_dir: Path, *, uids: Optional[Sequence[str]] = None
) -> List[str]:
    """Physically remove tombstoned projection files — the ONE operation that deletes (K001).

    Deliberately separate from retirement, and deliberately narrow: it refuses to remove a
    live object even when named. Compaction is an archival decision an operator makes about
    history they have already agreed is dead; nothing on the merge path can reach it.

    Returns the uids whose files were removed.
    """
    projection_dir = Path(projection_dir)
    documents = read_projection(projection_dir)
    targets = sorted(documents) if uids is None else sorted(set(uids))
    removed: List[str] = []
    for uid in targets:
        document = documents.get(uid)
        if not is_tombstoned(document):
            continue
        path = projection_dir / f"{uid}{PROJECTION_SUFFIX}"
        if path.is_file():
            path.unlink()
            removed.append(uid)
    if removed:
        _log.info("archival compaction removed tombstoned objects", extra={"uids": removed})
    return removed
