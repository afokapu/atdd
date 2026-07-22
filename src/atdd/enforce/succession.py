# URN: component:verify-enforcement:succession-coverage-proof:backend:domain
# Runtime: python
# Purpose: Prove, for every core convention node an extension mirrors, whether its
#          twin is bound AND blockingly running in CI — the retirement precondition
#          the govern-registry succession guard consumes. Pure domain + committed-
#          file loaders; no provider spawn.
"""Succession-coverage proof (#1429 WMBT E001).

This module PRODUCES ``commons:succession-coverage``; the govern-registry
succession guard (#1427 E003, :func:`atdd.enforce.registry.guard_core_deletion`)
CONSUMES it. Together they are the answer to one question: *can deleting a core
convention node silently drop the rule its extension twin was meant to inherit?*

Every extension node is a ``high_fidelity`` MIRROR of a live core rule, named by
its ``source.legacy_rule_id``. Under the advisory Path B that CI runs today that
core twin is the ONLY blocking enforcement of the shared obligation — so a core
node may be retired safely only when its succession is genuinely COVERED:

* **no twin mirrors it** — nothing else claims the obligation, nothing is lost; or
* **the twin is bound AND Path B is a blocking gate** — the twin independently
  enforces the rule once the core node is gone.

Any other twinned core rule is uncovered: retiring it strips the sole blocking
enforcement. Being *bound* is necessary but NOT sufficient — a bound twin whose
verdict is advisory enforces nothing.

:func:`succession_coverage` is the proof (one record per mirrored core rule);
:func:`retirement_precondition_holds` is the verdict the guard consumes;
:func:`assert_succession_covered` is the loud form. By construction the
precondition holds exactly when :func:`~atdd.enforce.registry.guard_core_deletion`
permits the deletion — producer and consumer cannot disagree.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from atdd.enforce.binding_gap import (
    load_bound_convention_ids,
    load_declared_extension_nodes,
)
from atdd.enforce.dispositions import STRICT
from atdd.enforce.registry import iter_extension_nodes, path_b_is_blocking


class SuccessionCoverageError(Exception):
    """A core rule may not be retired — its extension twin does not cover the succession."""


@dataclass(frozen=True)
class SuccessionCoverage:
    """One core rule's succession coverage — a ``commons:succession-coverage`` record.

    ``rule_id`` is the CORE rule the extension twin mirrors (its
    ``source.legacy_rule_id``), and ``disposition`` is that twin's treatment.
    """

    rule_id: str
    disposition: str
    twin_bound: bool
    path_b_blocking: bool

    @property
    def retirement_safe(self) -> bool:
        """Whether the core node may be retired without dropping the rule.

        BOTH conditions are required: a bound twin under an advisory Path B
        enforces nothing, so it does not make retirement safe.
        """
        return self.twin_bound and self.path_b_blocking

    def as_payload(self) -> dict:
        """The ``commons:succession-coverage`` payload (see the contract schema)."""
        return {"rule_id": self.rule_id, "disposition": self.disposition}


def succession_coverage(
    substrate_home: str | Path, *, path_b_blocking: bool
) -> list:
    """One :class:`SuccessionCoverage` record per core rule an extension mirrors.

    A core rule NO extension mirrors gets no record — there is no twin enforcement
    to lose, so its retirement was never at risk (see
    :func:`retirement_precondition_holds`).
    """
    bound = load_bound_convention_ids(substrate_home)
    declared = load_declared_extension_nodes(substrate_home)

    twins: dict[str, list] = {}
    for node in iter_extension_nodes(substrate_home):
        if node.legacy_rule_id:
            twins.setdefault(node.legacy_rule_id, []).append(node)

    coverage: list = []
    for core_rule_id, nodes in sorted(twins.items()):
        bound_twins = [n for n in nodes if n.rule_id in bound]
        # Report the BOUND twin's treatment when there is one — it is the twin whose
        # disposition decides whether the succeeding enforcement actually gates.
        representative = bound_twins[0] if bound_twins else nodes[0]
        coverage.append(
            SuccessionCoverage(
                rule_id=core_rule_id,
                disposition=declared.get(representative.rule_id, STRICT),
                twin_bound=bool(bound_twins),
                path_b_blocking=path_b_blocking,
            )
        )
    return coverage


def retirement_precondition_holds(
    core_rule_id: str, coverage: Iterable[SuccessionCoverage]
) -> bool:
    """Whether *core_rule_id* may be retired — the verdict the succession guard consumes.

    Holds when no extension node mirrors the rule (nothing to lose), or when every
    record for it is retirement-safe. This is exactly the condition under which
    :func:`atdd.enforce.registry.guard_core_deletion` permits the deletion.
    """
    records = [c for c in coverage if c.rule_id == core_rule_id]
    if not records:
        return True  # no twin mirrors it → no twin enforcement to lose
    return all(c.retirement_safe for c in records)


def render_succession_coverage_report(uncovered: Sequence[SuccessionCoverage]) -> str:
    """A loud report naming each core rule whose succession is not covered."""
    lines = [
        f"succession-coverage: {len(uncovered)} core convention node(s) may NOT be "
        f"retired — their extension twin does not cover the succession:",
    ]
    for c in uncovered:
        reason = (
            "its extension twin is not bound in binding.lock — no independent "
            "enforcement exists"
            if not c.twin_bound
            else "its extension twin is bound but Path B (atdd enforce) is advisory, "
            "not a blocking CI gate — retiring the core node strips the sole "
            "blocking enforcement"
        )
        lines.append(f"  [uncovered] {c.rule_id} — {reason}")
    return "\n".join(lines)


def assert_succession_covered(
    core_rule_ids: Iterable[str],
    substrate_home: str | Path,
    *,
    path_b_blocking: bool,
) -> list:
    """Raise :class:`SuccessionCoverageError` naming every core rule whose succession
    is not covered; else return the coverage records for the named rules.

    The precondition, asserted: a core node may only be retired once its twin
    genuinely succeeds it.
    """
    coverage = succession_coverage(substrate_home, path_b_blocking=path_b_blocking)
    wanted = set(core_rule_ids)
    records = [c for c in coverage if c.rule_id in wanted]
    uncovered = sorted(
        (c for c in records if not c.retirement_safe), key=lambda c: c.rule_id
    )
    if uncovered:
        raise SuccessionCoverageError(render_succession_coverage_report(uncovered))
    return records


def live_succession_coverage(repo_root: str | Path) -> list:
    """The succession-coverage proof over the REAL substrate and the REAL CI workflow."""
    return succession_coverage(repo_root, path_b_blocking=path_b_is_blocking(repo_root))
