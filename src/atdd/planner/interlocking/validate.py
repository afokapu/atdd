# URN: component:plan:train-interlocking:Validate:backend:application
# Runtime: python
# Purpose: Semantic cross-checks for an interlocking, beyond JSON-schema shape (#1248).
"""Semantic validation for interlockings.

The JSON schema validates *shape*; this module validates *meaning*: that message
endpoints resolve to declared lifelines, boundary/self message direction rules
hold, route guard references exist, route category/digit/train agree, and target
trains exist on disk. Returns a list of structured :class:`Violation` records
(empty when the interlocking is sound). Station Master reachability is NOT checked
here — that is delegated to extension validators (atdd-extensions#27).
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from .models import CATEGORY_BY_DIGIT, TrainInterlocking
from .violations import Violation

__all__ = ["validate_interlocking"]

_RULE = "PLAN-INTERLOCKING"


def _loc(interlocking: TrainInterlocking, suffix: str) -> str:
    base = interlocking.source.path or (
        str(interlocking.loaded_from) if interlocking.loaded_from else "interlocking"
    )
    return f"{base}:{suffix}"


def validate_interlocking(
    interlocking: TrainInterlocking, root: Path | str
) -> List[Violation]:
    """Return semantic violations for ``interlocking`` (empty list when sound)."""
    root = Path(root)
    violations: List[Violation] = []
    lifelines = interlocking.lifeline_refs()
    guards = interlocking.guard_index()

    # --- messages: endpoints + boundary/self direction ------------------------
    for msg in interlocking.messages:
        for endpoint in (msg.sender, msg.recipient):
            if endpoint not in lifelines:
                violations.append(
                    Violation(
                        rule_id=f"{_RULE}-001",
                        severity=3,
                        location=_loc(interlocking, msg.id),
                        detail=(
                            f"message {msg.id} endpoint {endpoint!r} is not a "
                            f"declared lifeline"
                        ),
                    )
                )
        if msg.kind == "boundary" and msg.sender == msg.recipient:
            violations.append(
                Violation(
                    rule_id=f"{_RULE}-002",
                    severity=3,
                    location=_loc(interlocking, msg.id),
                    detail=(
                        f"boundary message {msg.id} requires from != to "
                        f"(both {msg.sender!r})"
                    ),
                )
            )
        if msg.kind == "self" and msg.sender != msg.recipient:
            violations.append(
                Violation(
                    rule_id=f"{_RULE}-003",
                    severity=3,
                    location=_loc(interlocking, msg.id),
                    detail=(
                        f"self message {msg.id} requires from == to "
                        f"({msg.sender!r} != {msg.recipient!r})"
                    ),
                )
            )

    # --- routes: guard ref, category/digit/train agreement, train existence ---
    for route in interlocking.routes:
        if route.guard_ref not in guards:
            violations.append(
                Violation(
                    rule_id=f"{_RULE}-004",
                    severity=4,
                    location=_loc(interlocking, route.route_id),
                    detail=(
                        f"route {route.route_id} references unknown guard "
                        f"{route.guard_ref!r}"
                    ),
                )
            )

        train_digit = route.train_id[1] if len(route.train_id) >= 2 else ""
        if route.category_digit != train_digit:
            violations.append(
                Violation(
                    rule_id=f"{_RULE}-005",
                    severity=4,
                    location=_loc(interlocking, route.route_id),
                    detail=(
                        f"route {route.route_id} category_digit "
                        f"{route.category_digit!r} does not match train "
                        f"{route.train_id!r} category digit {train_digit!r}"
                    ),
                )
            )

        expected_category = CATEGORY_BY_DIGIT.get(route.category_digit)
        if expected_category is not None and route.category != expected_category:
            violations.append(
                Violation(
                    rule_id=f"{_RULE}-006",
                    severity=3,
                    location=_loc(interlocking, route.route_id),
                    detail=(
                        f"route {route.route_id} category {route.category!r} does not "
                        f"match category_digit {route.category_digit!r} "
                        f"(expected {expected_category!r})"
                    ),
                )
            )

        train_file = root / route.train_path
        if not train_file.exists():
            violations.append(
                Violation(
                    rule_id=f"{_RULE}-007",
                    severity=4,
                    location=_loc(interlocking, route.route_id),
                    detail=(
                        f"route {route.route_id} references missing train file "
                        f"{route.train_path}"
                    ),
                )
            )

    return violations
