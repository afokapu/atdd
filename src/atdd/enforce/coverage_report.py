# URN: component:verify-enforcement:enforcement-coverage-report:backend:domain
# Runtime: python
# Purpose: Name which extension rules CI actually ENFORCES versus merely REPORTS,
#          so the binding lock is never read as a statement of enforcement. Pure
#          domain + committed-file loaders; no provider spawn.
"""Enforcement-coverage report (#1429 WMBT M001).

Reading the binding lock and concluding "these rules are enforced" is the mistake
this module exists to prevent. **The bound set is not the enforced set.** A bound
extension convention only gates CI when all three hold:

1. it is ``bound`` in ``binding.lock.yaml`` (a mechanism exists), AND
2. its treatment FAILS on violation — ``strict`` / ``suppress-and-clean``; an
   ``advisory`` or ``documentation-only`` node reports without ever failing the
   build (:func:`atdd.enforce.dispositions.fails_on_violation`), AND
3. Path B — ``atdd enforce`` over the extensions — runs as a BLOCKING CI gate.

Condition (2) is deliberately NOT ``binding_gap.GATING_DISPOSITIONS``: that set
answers a different question — *must this node be BOUND?* — and so includes
``advisory``, because an advisory node still needs a detector to run in order to
report at all. Conflating the two is exactly how an advisory rule gets miscounted
as enforced.

Today (3) is false: the ``enforce-extensions`` job surfaces the convention verdict
advisory-only, so *every* bound extension rule is REPORTED, not enforced, and the
50 extension rules are enforced solely by their blocking core twin under Path A.
That is the latent hole. This report NAMES it instead of leaving it to be inferred:
every declared extension rule is classified :data:`ENFORCED`, :data:`REPORTED`, or
:data:`UNBOUND`, and the render states the gap outright when the two sets differ.

:func:`build_coverage_report` is the pure classification over a
declared-with-disposition map, a bound set, and the Path-B verdict;
:func:`live_coverage_report` runs it over the toolkit's own committed substrate
and real CI workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from atdd.enforce.binding_gap import (
    load_bound_convention_ids,
    load_declared_extension_nodes,
)
from atdd.enforce.dispositions import fails_on_violation
from atdd.enforce.registry import path_b_is_blocking

#: Violations of this rule FAIL CI — a bound gating node under a blocking Path B.
ENFORCED = "enforced"
#: Violations are surfaced but gate nothing — a bound node that is advisory or
#: documentation-only, or any bound node while Path B stays advisory.
REPORTED = "reported"
#: No mechanism is bound, so the rule is neither enforced nor even reported.
UNBOUND = "unbound"


def classify_enforcement(
    disposition: str, *, bound: bool, path_b_blocking: bool
) -> str:
    """Classify one rule's REAL enforcement status in CI. Total over its inputs.

    An unbound rule runs no detector at all (:data:`UNBOUND`). A bound rule gates
    only when its treatment FAILS on violation AND Path B is a blocking gate;
    otherwise its verdict is produced but ignored (:data:`REPORTED`).

    The predicate is :func:`~atdd.enforce.dispositions.fails_on_violation`, NOT
    ``binding_gap.GATING_DISPOSITIONS`` — the two are different questions that a
    reader easily conflates. ``GATING_DISPOSITIONS`` answers *must this node be
    BOUND?* and so includes ``advisory`` (an advisory node still needs a detector
    to run, or it cannot even report). ``fails_on_violation`` answers *do this
    node's violations FAIL the build?* and excludes ``advisory``. Enforcement
    coverage is the second question: an advisory rule is REPORTED, never ENFORCED.
    """
    if not bound:
        return UNBOUND
    if not fails_on_violation(disposition):
        return REPORTED  # advisory / documentation-only never fail the build
    return ENFORCED if path_b_blocking else REPORTED


@dataclass(frozen=True)
class CoverageRecord:
    """One extension rule's declared treatment, binding state, and real status."""

    rule_id: str
    disposition: str
    bound: bool
    status: str


@dataclass(frozen=True)
class CoverageReport:
    """The classified universe of declared extension rules — the coverage truth."""

    records: tuple
    path_b_blocking: bool

    def _ids(self, status: str) -> list:
        return sorted(r.rule_id for r in self.records if r.status == status)

    @property
    def enforced(self) -> list:
        """Rules whose violations actually FAIL CI."""
        return self._ids(ENFORCED)

    @property
    def reported(self) -> list:
        """Rules whose violations are surfaced but gate nothing."""
        return self._ids(REPORTED)

    @property
    def unbound(self) -> list:
        """Rules with no bound mechanism at all."""
        return self._ids(UNBOUND)

    @property
    def bound(self) -> list:
        """Rules the lock binds — deliberately NOT the same thing as ``enforced``."""
        return sorted(r.rule_id for r in self.records if r.bound)

    @property
    def coverage_is_honest(self) -> bool:
        """True iff every bound rule is genuinely enforced — no bound-but-not-enforced gap."""
        return self.enforced == self.bound


def build_coverage_report(
    declared: Mapping[str, str],
    bound: Iterable[str],
    *,
    path_b_blocking: bool,
) -> CoverageReport:
    """Classify every declared extension rule. Pure — stable for any inputs."""
    bound_ids = set(bound)
    records = tuple(
        CoverageRecord(
            rule_id=cid,
            disposition=disposition,
            bound=cid in bound_ids,
            status=classify_enforcement(
                disposition, bound=cid in bound_ids, path_b_blocking=path_b_blocking
            ),
        )
        for cid, disposition in sorted(declared.items())
    )
    return CoverageReport(records=records, path_b_blocking=path_b_blocking)


def render_coverage_report(report: CoverageReport) -> str:
    """The human-readable coverage truth: which rules gate CI, and which only talk.

    Each rule is listed exactly once under its status group. When the bound set
    exceeds the enforced set the gap is STATED, so a reader can never mistake the
    lock for a statement of enforcement.
    """
    gate = "BLOCKING" if report.path_b_blocking else "advisory (non-blocking)"
    lines = [
        f"enforcement-coverage: {len(report.enforced)} ENFORCED, "
        f"{len(report.reported)} REPORTED-only, {len(report.unbound)} UNBOUND "
        f"(Path B is {gate})",
    ]

    for status, heading, note in (
        (ENFORCED, "ENFORCED in CI", "violations FAIL the build"),
        (REPORTED, "REPORTED only", "violations are surfaced but gate nothing"),
        (UNBOUND, "UNBOUND", "no bound mechanism — not even reported"),
    ):
        members = [r for r in report.records if r.status == status]
        if not members:
            continue
        lines.append(f"  {heading} ({note}):")
        for r in sorted(members, key=lambda m: m.rule_id):
            lines.append(f"    [{status}] {r.rule_id} — disposition={r.disposition}")

    if not report.coverage_is_honest:
        missing = len(report.bound) - len(report.enforced)
        lines.append(
            f"  WARNING: the bound set is not the enforced set — {missing} of "
            f"{len(report.bound)} bound rule(s) do not gate CI. Their obligations are "
            f"enforced only by their core twin (Path A); retiring that twin would "
            f"silently drop the rule."
        )
    return "\n".join(lines)


def live_coverage_report(
    substrate_home: str | Path, repo_root: str | Path
) -> CoverageReport:
    """The coverage report over the REAL substrate and the REAL CI workflow."""
    return build_coverage_report(
        load_declared_extension_nodes(substrate_home),
        load_bound_convention_ids(substrate_home),
        path_b_blocking=path_b_is_blocking(repo_root),
    )
