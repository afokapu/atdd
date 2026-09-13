# URN: component:govern-registry:declared-retirements:backend:domain
# Runtime: python
# Purpose: Carry the one fact that separates a sanctioned core-rule retirement from a
#          stale mirror — a declaration, keyed on the retired core rule_id, naming the
#          issue that retired it and what succeeds it.
"""Declared retirements (#1714 / wmbt:govern-registry:E004).

Mirror coherence sees three states and can only tell two of them apart:

===========================  ====================  ==========  ==============
state                        ``legacy_rule_id``    correct     without this
===========================  ====================  ==========  ==============
stale mirror (RENAMED)       names a dead id       FAIL        FAIL
carve-out (DELETED on        names a dead id       pass        FAIL
purpose, node superseded it)
extension-native obligation  absent                pass        FAIL
===========================  ====================  ==========  ==============

The first two are **identical in the data** — both present a legacy id naming a core
rule that is not there — so the difference is not recoverable by reading the node
harder. It has to be declared. That is this ledger.

It is the same fact :func:`~atdd.enforce.registry.evaluate_core_deletion` is missing:
its twinless branch cannot tell *deliberately retiring* a rule from *moving it and
forgetting to bring it* (#1993 Phase 2). One declaration serves both guards; two would
be two things to keep in step.

**Absence is never the licence.** A missing ledger retires NOTHING and every drifted
mirror stays reported. Read the other way — no file, so nothing is policed — it would
silently green the one gate watching for a lost obligation. Note this is the opposite
default to :func:`atdd.enforce.ratchet.load_baseline`, which RAISES on a missing
baseline: there, absence read as forgiveness would forgive real debt. Same principle
(never let a missing file weaken a gate), opposite mechanics, because the file means
opposite things.

An entry must name the issue that retired the rule. A retirement asserted with no
evidence it was sanctioned is indistinguishable from one invented to silence a red
gate, so it is refused rather than admitted. ``superseded_by`` may be empty: a rule
genuinely withdrawn is a real outcome, and it must be sayable apart from one whose
succession was simply forgotten.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

__all__ = [
    "RETIREMENTS_PATH",
    "Retirement",
    "RetirementError",
    "declared_retirements",
    "parse_retirements",
]

#: The ledger's location, relative to the substrate home — alongside the other
#: committed ``.atdd/`` registers (``binding.lock.yaml``, ``enforce-ratchet.yaml``).
RETIREMENTS_PATH: str = ".atdd/retirements.yaml"


class RetirementError(Exception):
    """A malformed ledger or an entry with no evidence — a usage error, never a pass."""


@dataclass(frozen=True)
class Retirement:
    """One sanctioned retirement of a core rule.

    ``superseded_by`` is empty when the rule was withdrawn outright rather than moved;
    that is a declaration in its own right, not a missing field.
    """

    rule_id: str
    retired_in: str
    superseded_by: tuple[str, ...]
    commit: str | None = None
    reason: str | None = None


def _entry(rule_id: str, body: Any) -> Retirement:
    if not isinstance(body, Mapping):
        raise RetirementError(
            f"retirement entry for {rule_id!r} must be a mapping, got {type(body).__name__}"
        )
    retired_in = body.get("retired_in")
    if not retired_in or not str(retired_in).strip():
        raise RetirementError(
            f"retirement entry for {rule_id!r} names no 'retired_in' — a retirement "
            "must carry the issue that sanctioned it, or it cannot be told from one "
            "invented to silence a red gate"
        )
    superseded = body.get("superseded_by")
    if superseded is None:
        raise RetirementError(
            f"retirement entry for {rule_id!r} omits 'superseded_by' — declare the "
            "rule(s) that now carry the obligation, or an empty list to say the rule "
            "was withdrawn outright; omitting it cannot be told from forgetting it"
        )
    if isinstance(superseded, str) or not isinstance(superseded, (list, tuple)):
        raise RetirementError(
            f"retirement entry for {rule_id!r} has a non-list 'superseded_by'"
        )
    return Retirement(
        rule_id=rule_id,
        retired_in=str(retired_in),
        superseded_by=tuple(str(s) for s in superseded),
        commit=(str(body["commit"]) if body.get("commit") else None),
        reason=(str(body["reason"]) if body.get("reason") else None),
    )


def parse_retirements(data: Any) -> dict[str, Retirement]:
    """Validate a loaded ledger document. Pure, so the rules are testable as rules."""
    if data is None:
        return {}
    if not isinstance(data, Mapping):
        raise RetirementError("retirement ledger must be a mapping at its root")
    entries = data.get("retirements")
    if entries is None:
        return {}
    if not isinstance(entries, Mapping):
        raise RetirementError("'retirements' must be a mapping of rule_id -> entry")
    return {str(rule_id): _entry(str(rule_id), body) for rule_id, body in entries.items()}


def declared_retirements(substrate_home: str | Path) -> dict[str, Retirement]:
    """Read ``.atdd/retirements.yaml`` under *substrate_home*.

    An absent ledger yields ``{}`` — nothing retired, everything still policed. An
    unreadable or malformed one RAISES: it was meant to say something, and guessing
    what would be guessing about which obligations may vanish.
    """
    path = Path(substrate_home) / RETIREMENTS_PATH
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RetirementError(f"unreadable retirement ledger at {path}: {exc}") from exc
    return parse_retirements(data)
