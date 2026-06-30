# URN: component:plan:train-interlocking:Digest:backend:domain
# Runtime: python
# Purpose: Deterministic, formatting-insensitive content digests (#1248).
"""Normalized digest semantics for interlockings and route projections.

A digest is computed by: parse YAML -> retain semantic fields -> canonicalize to
a deterministic key order -> hash the UTF-8 bytes. The digest therefore changes
when route semantics change but is stable across irrelevant formatting changes
(key order, flow vs block style, quoting). Stdlib-only; no IO.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, List, Mapping, Sequence, Tuple

__all__ = ["normalized_interlocking_digest", "route_projection_digest", "canonicalize"]


def canonicalize(value: Any) -> str:
    """Deterministic canonical JSON for ``value`` (sorted keys, stable separators)."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _strip_derived(data: Mapping[str, Any]) -> dict:
    """Drop self-referential derived fields that must not feed their own digest.

    Only ``source.content_digest`` is excluded — it is the digest of everything
    else, so including it would be circular. The per-route
    ``projection.expected_sequence_digest`` values ARE authored assertions and so
    remain part of the semantic content.
    """
    clone = json.loads(json.dumps(data))  # deep copy via round-trip (data is YAML-plain)
    src = clone.get("source")
    if isinstance(src, dict):
        src.pop("content_digest", None)
    return clone


def normalized_interlocking_digest(data: Mapping[str, Any]) -> str:
    """sha256 (hex) of the normalized interlocking content."""
    canonical = canonicalize(_strip_derived(data))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def route_projection_digest(
    steps: Sequence[Any], fields: Iterable[str]
) -> str:
    """sha256 (hex) of a route's projected linear train sequence.

    ``steps`` are ``TrainStep`` instances; ``fields`` is the ordered projection
    field selection. Each step is rendered as an ordered list of (field, value)
    pairs so both step order and field order are part of the digest.
    """
    field_tuple: Tuple[str, ...] = tuple(fields)
    rendered: List[List[List[Any]]] = []
    for step in steps:
        rendered.append([[k, v] for k, v in step.as_projection(field_tuple)])
    payload = {"fields": list(field_tuple), "steps": rendered}
    # field/step order is significant -> do NOT sort keys for the ordered lists;
    # canonicalize only stabilizes the small wrapper mapping.
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
