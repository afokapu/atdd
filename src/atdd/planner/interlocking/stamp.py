# URN: component:plan:train-interlocking:Stamp:backend:application
# Runtime: python
# Purpose: Derive + stamp an interlocking's digests at authoring write-time (#1265).
"""Stamp the derived digests onto an interlocking document (#1265).

The control body of an interlocking (guards, entrypoint, routes, strategy,
messages, fragments, invariants, residuals) is human-authored input. The *only*
parts of the artifact that are mechanically derived are the digests:

  * each ``route.projection.expected_sequence_digest`` — the sha256 of the route's
    target train's linear projected sequence, and
  * ``source.content_digest`` — the sha256 of the whole normalized document.

``stamp_interlocking_digests`` composes the existing #1248 digest math
(``project_route_to_train_sequence`` -> ``route_projection_digest`` per route,
then ``normalized_interlocking_digest`` over the whole doc) — it never
re-implements that math, so the stamp is byte-identical to what the #1249 Confirm
gate independently recomputes. This is the single source of truth for an
interlocking's digests at authoring time.

The function is pure (returns a new dict; never writes) and naturally idempotent:
re-stamping an already-stamped document converges to the same bytes, because the
normalized digest strips ``source.content_digest`` before hashing and the route
digests are recomputed from the on-disk trains.

Precondition: every ``route.train_path`` train YAML must already exist on disk
(``create_train`` runs before ``create_interlocking``). A missing train raises
:class:`InterlockingError` *before* any value is returned, so the caller never
writes a partial / half-stamped artifact.

Stdlib + the #1248 interlocking API only; no other-layer imports (boundaries
§3.3).
"""
from __future__ import annotations

import copy
import dataclasses
from pathlib import Path
from typing import Any, Mapping

from .digest import normalized_interlocking_digest, route_projection_digest
from .loader import parse_interlocking
from .projections import project_route_to_train_sequence

__all__ = ["stamp_interlocking_digests"]


def stamp_interlocking_digests(doc: Mapping[str, Any], root: Path | str) -> dict:
    """Return a deep copy of ``doc`` with its derived digests stamped.

    ``root`` is the repo root the route ``train_path`` values resolve against.
    Raises :class:`InterlockingError` (via the #1248 loader / projection) when the
    document is shape-invalid or a route's target train is missing on disk; in
    that case the function raises before returning, so the caller writes nothing.
    """
    root = Path(root)
    stamped: dict = copy.deepcopy(dict(doc))

    # Parse to the typed model to reuse the EXACT field selection the #1249 gate
    # uses (``projection.fields`` defaults to the canonical 5-tuple when omitted),
    # and bind the repo root so ``project_route_to_train_sequence`` can load each
    # route's on-disk train. Placeholder digests on the input are fine — they are
    # never read here, only overwritten.
    model = parse_interlocking(stamped)  # shape-validates; raises InterlockingError on bad shape
    model = dataclasses.replace(model, repo_root=root)

    # 1) Per-route expected_sequence_digest, derived from the route's on-disk train.
    for route_dict in stamped.get("routes", []):
        route = model.route_by_id(route_dict["route_id"])
        steps = project_route_to_train_sequence(model, route.route_id)
        projection = route_dict.setdefault("projection", {})
        projection["expected_sequence_digest"] = route_projection_digest(
            steps, route.projection.fields
        )

    # 2) Whole-document content_digest over the now route-stamped content. The
    #    normalized digest strips ``source.content_digest`` before hashing, so the
    #    existing placeholder/value never feeds its own hash (idempotency).
    stamped.setdefault("source", {})["content_digest"] = normalized_interlocking_digest(
        stamped
    )
    return stamped
