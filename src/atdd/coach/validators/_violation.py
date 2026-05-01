# URN: component:govern-lifecycle:enforcement-substrate:Violation:backend:domain
# Runtime: python
# Purpose: Structured violation record passed from validators to ratchet/risk-routing/self-fix.

"""
Structured violation record for the validator substrate.

A `Violation` is the durable, machine-addressable form of "a rule was broken
here". Validators emit a list of these instead of bare prose; the ratchet
persists them additively next to the integer-count baseline; downstream
tooling (risk-scoring, suppression audit, self-fix recipes) keys off
``rule_id`` to route work.

Grammar and lifecycle are documented in
``src/atdd/coach/specs/rule-id.spec.md``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Violation:
    """One concrete instance of a rule being broken in the repo.

    Attributes:
        rule_id: Stable rule identifier matching the grammar
            ``<DOMAIN>-<TOPIC>-<NNN>`` (see rule-id.spec.md). Persisted
            forever; renames go through ``superseded_by``.
        severity: Integer 1 (advisory) to 5 (security/blocking). Sums into
            a risk score for PR routing.
        location: ``path:line`` or ``path:line:col`` of the offending site,
            relative to the repo root.
        detail: One-line human-readable description of *this* instance.
        fix_hint_ref: Optional pointer to a fix recipe step, e.g.
            ``recipe:adapter#step-1``. Consumed by self-fix tooling.
    """

    rule_id: str
    severity: int
    location: str
    detail: str
    fix_hint_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.severity, int) or not (1 <= self.severity <= 5):
            raise ValueError(
                f"severity must be int in [1, 5], got {self.severity!r}"
            )
        if not self.rule_id:
            raise ValueError("rule_id is required")
        if not self.location:
            raise ValueError("location is required (use 'path:line')")

    def to_dict(self) -> Dict[str, Any]:
        """Serializable mapping for YAML/JSON persistence."""
        d = asdict(self)
        if d["fix_hint_ref"] is None:
            d.pop("fix_hint_ref")
        return d

    def __str__(self) -> str:
        ref = f" → {self.fix_hint_ref}" if self.fix_hint_ref else ""
        return f"[{self.rule_id} sev={self.severity}] {self.location}: {self.detail}{ref}"


__all__ = ["Violation"]
