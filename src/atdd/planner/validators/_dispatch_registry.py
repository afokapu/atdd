# Phase: GREEN
# Layer: backend.domain
"""Dispatch-registry entry checks for plan/_dispatch.yaml (#1043 / #1034, extracted #1385).

Pure predicates over a single dispatch entry:

- ``check_entry_shape`` — an entry routes a divergence artifact to a train.
- ``check_composite_key_exceptional`` — a composite ``(artifact_urn, discriminant)``
  key is permitted ONLY with a ``behavioral_difference`` justification, and the
  discriminant is exactly one field:value (canonical case:
  ``commons:decision:escalation.cause``, #1083).

Both return ``None`` when the entry is well-formed, else a violation detail string.

Enforcement lives in the convention variant
``validators/conventions/schema/test_dispatch_map_is_registry.py``; this module holds the
predicates so they outlive the retired legacy validator
(``planner/validators/test_dispatch_registry.py``, #1207 sweep).
"""
from __future__ import annotations

from typing import Optional


def check_entry_shape(entry: dict) -> Optional[str]:
    """Every dispatch entry routes a divergence artifact to a train."""
    if not isinstance(entry, dict):
        return f"dispatch entry must be a mapping, got {type(entry).__name__}"
    if not entry.get("artifact_urn") or not entry.get("train_id"):
        return f"dispatch entry missing artifact_urn/train_id: {entry!r}"
    return None


def check_composite_key_exceptional(entry: dict) -> Optional[str]:
    """A composite key (entry carries ``discriminant``) must be exactly one
    field:value AND carry a ``behavioral_difference`` justification."""
    if "discriminant" not in entry:
        return None
    urn = entry.get("artifact_urn", "<unknown>")
    disc = entry["discriminant"]
    if not isinstance(disc, dict) or len(disc) != 1:
        return (f"{urn}: composite `discriminant` must be exactly one field:value, "
                f"got {disc!r}")
    if not entry.get("behavioral_difference"):
        return (f"{urn}: composite key on {disc!r} requires a `behavioral_difference` "
                f"justification (dispatch-composite-key-exceptional)")
    return None
