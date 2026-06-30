# URN: component:plan:train-interlocking:Violation:backend:domain
# Runtime: python
# Purpose: Structured violation record for interlocking semantic validation (#1248).
"""Structured violation record for interlocking validation.

Mirrors the canonical validator-substrate ``Violation`` shape (rule_id/severity/
location/detail/fix_hint_ref) so #1249's planner validators can lift these records
into the registry, but is defined locally so the planner interlocking artifact has
no production-time dependency on ``atdd.coach`` (keeps the library consumable by
runtime/extension code without pulling in coach machinery). Stdlib-only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

__all__ = ["Violation"]


@dataclass(frozen=True)
class Violation:
    """One concrete instance of an interlocking rule being broken.

    Field names and the ``[1, 5]`` severity invariant match the canonical
    validator-substrate record (see ``src/atdd/coach/specs/rule-id.spec.md``).
    """

    rule_id: str
    severity: int
    location: str
    detail: str
    fix_hint_ref: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.severity, int) or not (1 <= self.severity <= 5):
            raise ValueError(f"severity must be int in [1, 5], got {self.severity!r}")
        if not self.rule_id:
            raise ValueError("rule_id is required")
        if not self.location:
            raise ValueError("location is required (use 'path:line')")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["fix_hint_ref"] is None:
            d.pop("fix_hint_ref")
        return d

    def __str__(self) -> str:
        ref = f" → {self.fix_hint_ref}" if self.fix_hint_ref else ""
        return f"[{self.rule_id} sev={self.severity}] {self.location}: {self.detail}{ref}"
