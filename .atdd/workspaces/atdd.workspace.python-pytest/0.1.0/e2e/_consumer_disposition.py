"""A FAITHFUL LOCAL STAND-IN for the downstream consumer's disposition gate.

This module represents core/coach — specifically
``atdd.coach.utils.disposition_gate.assert_disposition_satisfied``. It is placed
here ONLY for the Phase-0.5 proof; in production it lives entirely OUTSIDE any
workspace provider. The point of the leading underscore + this docstring is to
make the boundary undeniable:

  * The provider adapter (../adapter/run.py) NEVER imports this module.
  * This module NEVER imports the provider adapter.
  * The only thing crossing the boundary is the RAW violation list
    ``[{rule_id, file, line, col, evidence, source_line}, ...]`` the provider
    emits — data, not code.

It is a faithful (not byte-for-byte) reduction of the core gate's decision logic:

  * Group raw violations by ``rule_id``.
  * Look up each rule's ``disposition`` from a registry (here: the two convention
    nodes' declared dispositions; unknown rule_id -> ``strict`` default, exactly
    as core does — see disposition_gate ``_DEFAULT_DISPOSITION``).
  * ``strict``             -> every violation is unsuppressed (markers ignored).
  * ``suppress-and-clean`` -> a violation is absorbed iff its ``source_line``
    carries ``atdd:suppress(<rule_id>)`` — the SAME substring contract as core
    ``suppression_scanner.is_suppressed``. (UNTIL staleness is NOT decided here;
    the core gate also absorbs on marker-present regardless of UNTIL — staleness
    is a separate validator's job.)
  * ``advisory``           -> violations warn and pass (never fail).

Final verdict: FAIL iff any unsuppressed violation exists across strict +
suppress-and-clean rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Disposition registry the consumer would build from the convention nodes.
# Faithful to the migrated nodes: print=strict, structured=suppress-and-clean.
DISPOSITIONS = {
    "coder.logging.print": "strict",
    "coder.logging.structured": "suppress-and-clean",
}
_DEFAULT_DISPOSITION = "strict"  # mirrors disposition_gate._DEFAULT_DISPOSITION


def is_suppressed(source_line: str, rule_id: str) -> bool:
    """Marker contract, mirrored verbatim from core suppression_scanner."""
    return f"atdd:suppress({rule_id})" in (source_line or "")


@dataclass(frozen=True)
class Verdict:
    passed: bool
    unsuppressed: list[dict] = field(default_factory=list)
    suppressed: list[dict] = field(default_factory=list)
    advisory: list[dict] = field(default_factory=list)
    by_rule: dict = field(default_factory=dict)  # rule_id -> {disposition,unsuppressed,suppressed}


def apply_disposition(violations: list[dict], dispositions: dict | None = None) -> Verdict:
    """Apply per-rule disposition to RAW provider violations -> a pass/fail verdict.

    ``violations`` is the provider's RAW output. ``dispositions`` is the rule->tier
    map (defaults to ``DISPOSITIONS``); unknown rule_ids default to ``strict``.
    """
    reg = dispositions if dispositions is not None else DISPOSITIONS
    unsuppressed: list[dict] = []
    suppressed: list[dict] = []
    advisory: list[dict] = []
    by_rule: dict = {}

    for v in violations:
        rule_id = v.get("rule_id", "")
        disp = reg.get(rule_id, _DEFAULT_DISPOSITION)
        bucket = by_rule.setdefault(
            rule_id, {"disposition": disp, "unsuppressed": 0, "suppressed": 0}
        )
        if disp == "advisory":
            advisory.append(v)
            continue
        if disp == "suppress-and-clean" and is_suppressed(v.get("source_line", ""), rule_id):
            suppressed.append(v)
            bucket["suppressed"] += 1
            continue
        # strict, OR suppress-and-clean with no marker -> counts against the gate.
        unsuppressed.append(v)
        bucket["unsuppressed"] += 1

    return Verdict(
        passed=(len(unsuppressed) == 0),
        unsuppressed=unsuppressed,
        suppressed=suppressed,
        advisory=advisory,
        by_rule=by_rule,
    )
