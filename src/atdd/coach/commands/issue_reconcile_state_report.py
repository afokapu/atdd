"""Report rendering + assembly for ``atdd coach reconcile-state`` (#1338).

Split out of ``issue_reconcile_state`` to keep both modules under the file-length
limit. The dependency runs one way — this module imports the classification core,
never the reverse — so ``build_report`` lives here alongside the renderer it
feeds rather than being stranded on the other side of the seam.

The report is the operator's approval surface: the verb reports by default and
mutates only when a human has read this table and said so.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from atdd.coach.commands.issue_reconcile_state import (
    CLASS_IN_SYNC,
    CLASS_NAMES,
    Repair,
)



@dataclass
class ReconcileReport:
    repairs: List[Repair] = field(default_factory=list)

    def by_class(self) -> Dict[int, List[Repair]]:
        buckets: Dict[int, List[Repair]] = {}
        for repair in self.repairs:
            buckets.setdefault(repair.repair_class, []).append(repair)
        return buckets

    def render(self, dry_run: bool = True) -> str:
        """The classification table the operator approves before anything writes."""
        lines: List[str] = []
        header = "reconcile-state — what WOULD change" if dry_run else "reconcile-state — applied"
        lines.append(header)
        lines.append("=" * len(header))
        lines.append("")

        buckets = self.by_class()
        drifted = [r for r in self.repairs if r.repair_class != CLASS_IN_SYNC]
        lines.append(
            f"{len(self.repairs)} record(s) examined — "
            f"{len(self.repairs) - len(drifted)} in sync, {len(drifted)} drifted"
        )
        lines.append("")

        for cls in sorted(buckets):
            lines.extend(_render_class_block(cls, buckets[cls]))

        if dry_run:
            lines.append(
                "DRY RUN — nothing was written. Re-run with `--apply` on a single "
                "issue number to repair it."
            )
        return "\n".join(lines)


def _planned_action(repair: Repair) -> str:
    """The remedy this repair would apply, in one phrase."""
    if repair.transitions:
        return " -> ".join(repair.transitions)
    if repair.reproject_to:
        return f"re-project label := {repair.reproject_to}"
    return "none"


def _class_marker(group: List[Repair]) -> str:
    """How the operator should read a whole class at a glance."""
    if any(r.refused for r in group):
        return "REFUSED"
    if all(r.is_noop for r in group):
        return "no-op"
    return "repairable"


def _render_class_block(cls: int, group: List[Repair]) -> List[str]:
    """One class heading plus a line per drifted record under it.

    In-sync records are counted in the heading but not listed — a report that
    prints 226 no-ops buries the 82 refusals the operator actually needs to see.
    """
    lines = [f"class {cls} — {CLASS_NAMES[cls]} [{_class_marker(group)}]: {len(group)}"]
    for repair in sorted(group, key=lambda r: r.issue_number):
        if repair.repair_class == CLASS_IN_SYNC:
            continue
        lines.append(
            f"    #{repair.issue_number:<6} "
            f"label={repair.label_phase or 'none':<9} "
            f"store={repair.store_phase or 'none':<9} "
            f"merged={'yes' if repair.merged else 'no':<3} "
            f"action: {_planned_action(repair)}"
        )
    lines.append("")
    return lines
