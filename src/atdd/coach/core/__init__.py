"""Coach-core — pure policy authority for the ATDD lifecycle.

The only public API is the five pure functions below. Each is a pure function of
``(Evidence, Conventions)`` (or ``(Phase, reports, Conventions)``): same inputs
always produce the same output. No I/O, no subprocess, no ``gh``/``git``/``cmux``,
no threading, no clock reads.

These are the **placeholder** implementations frozen by Child 1
(docs/coach-decomposition.md §4.3, §13.1). They read policy out of the frozen
``Conventions`` bundle (phase machine + rules) and return typed verdicts; the
richer evidence-evaluation logic is migrated out of ``coach.commands.coach`` in
later children. The typed signatures are the contract every downstream layer
binds to and MUST stay stable.

PURITY: enforced by the import-discipline test (Child 2). Do not add I/O here.
"""
from __future__ import annotations

from atdd.coach.core.types import (
    CiState,
    Conventions,
    Evidence,
    MergeVerdict,
    Persona,
    Phase,
    PhaseSpec,
    TransitionDecision,
    ValidatorReport,
    Verdict,
    VerdictKind,
)

# Phases that are non-advancing terminals (no forward successor).
_TERMINAL_PHASES: frozenset[Phase] = frozenset({Phase.COMPLETE, Phase.OBSOLETE})

# Phase labels that are escape hatches rather than forward progress.
_NON_FORWARD_TARGETS: frozenset[Phase] = frozenset({Phase.BLOCKED, Phase.OBSOLETE})

# Placeholder no-progress TTL (seconds). The real value moves to Conventions when
# escalation policy is migrated; kept as a module constant so the function stays
# pure and self-contained (I-7 no-progress TTL escalation).
DEFAULT_NO_PROGRESS_TTL_SECONDS: int = 86_400

# Phases from which a merge may be considered (REFACTOR onward).
_MERGE_ELIGIBLE_PHASES: frozenset[Phase] = frozenset({Phase.REFACTOR, Phase.COMPLETE})


def _rule(phase: Phase, suffix: str) -> str:
    """Stable placeholder rule id keyed on phase + concern."""
    return f"coach.core.{phase.value.lower()}.{suffix}"


def _blocking_reports(reports: tuple[ValidatorReport, ...]) -> tuple[ValidatorReport, ...]:
    return tuple(r for r in reports if r.disposition == "block" and r.unsuppressed_count > 0)


def _forward_target(spec: PhaseSpec) -> Phase | None:
    """The single happy-path successor: first transition that is real progress."""
    for candidate in spec.transitions_to:
        if candidate not in _NON_FORWARD_TARGETS:
            return candidate
    return None


def evaluate_evidence(evidence: Evidence, conventions: Conventions) -> Verdict:
    """Pure. Given evidence, is the current phase satisfied? PROCEED/STAY/BLOCKED."""
    phase = evidence.current_phase

    if phase in _TERMINAL_PHASES:
        return Verdict(
            kind=VerdictKind.STAY,
            reason=f"{phase} is terminal; nothing to advance",
            rule_ids=(_rule(phase, "terminal"),),
        )

    blockers = _blocking_reports(evidence.validator_reports)
    if blockers:
        return Verdict(
            kind=VerdictKind.BLOCKED,
            reason=f"{len(blockers)} blocking validator report(s) in {phase}",
            rule_ids=tuple(r.rule_id for r in blockers),
            fix_hint="resolve the blocking validator violations, then resume",
        )

    if evidence.ci_state in (CiState.PENDING, CiState.NONE):
        return Verdict(
            kind=VerdictKind.STAY,
            reason=f"CI {evidence.ci_state} in {phase}; waiting",
            rule_ids=(_rule(phase, "ci-wait"),),
            retry_after_seconds=60,
        )

    if evidence.ci_state == CiState.FAILURE:
        return Verdict(
            kind=VerdictKind.STAY,
            reason=f"CI failing in {phase}; awaiting worker fix",
            rule_ids=(_rule(phase, "ci-failure"),),
            retry_after_seconds=60,
        )

    return Verdict(
        kind=VerdictKind.PROCEED,
        reason=f"{phase} gate satisfied",
        rule_ids=(_rule(phase, "advance"),),
    )


def next_transition(evidence: Evidence, conventions: Conventions) -> TransitionDecision:
    """Pure. Look up the current phase, evaluate gates, return the decision.

    Never reads files, never calls gh, never spawns anything.
    """
    phase = evidence.current_phase
    spec = conventions.phase_machine[phase]
    verdict = evaluate_evidence(evidence, conventions)
    forward = _forward_target(spec)

    if verdict.kind is VerdictKind.PROCEED and forward is not None:
        persona = spec.agent
        template_id = f"{persona.value}.{forward.value.lower()}" if persona is not None else None
        return TransitionDecision(
            from_phase=phase,
            to_phase=forward,
            persona=persona,
            prompt_template_id=template_id,
            evidence_keys_required=tuple(sorted(evidence.artifacts_present)),
            verdict=verdict,
        )

    return TransitionDecision(
        from_phase=phase,
        to_phase=None,
        persona=None,
        prompt_template_id=None,
        evidence_keys_required=(),
        verdict=verdict,
    )


def review_phase_output(
    phase: Phase,
    reports: tuple[ValidatorReport, ...],
    conventions: Conventions,
) -> Verdict:
    """Pure. Given validator reports, has this phase's exit criteria been met?"""
    blockers = _blocking_reports(reports)
    if blockers:
        return Verdict(
            kind=VerdictKind.BLOCKED,
            reason=f"{len(blockers)} blocking report(s) at {phase} exit",
            rule_ids=tuple(r.rule_id for r in blockers),
            fix_hint="resolve the blocking validator violations before advancing",
        )
    return Verdict(
        kind=VerdictKind.PROCEED,
        reason=f"{phase} exit criteria met",
        rule_ids=(_rule(phase, "exit"),),
    )


def merge_readiness(evidence: Evidence, conventions: Conventions) -> MergeVerdict:
    """Pure. Can the PR for this issue be merged right now?"""
    blockers: list[str] = []

    if evidence.current_phase not in _MERGE_ELIGIBLE_PHASES:
        blockers.append(f"phase {evidence.current_phase} is before merge-eligible REFACTOR")

    pr = evidence.pr_state
    if pr is None:
        blockers.append("no PR open for this issue")
    elif pr.state != "OPEN":
        blockers.append(f"PR is {pr.state}, not OPEN")
    elif pr.mergeable == "CONFLICTING":
        blockers.append("PR is CONFLICTING")

    if evidence.ci_state != CiState.SUCCESS:
        blockers.append(f"CI is {evidence.ci_state}, not success")

    for report in _blocking_reports(evidence.validator_reports):
        blockers.append(report.validator_id)

    return MergeVerdict(
        can_merge=not blockers,
        blockers=tuple(blockers),
        required_label=Phase.REFACTOR,
    )


def escalation_for(evidence: Evidence, conventions: Conventions) -> Verdict | None:
    """Pure. Detect escalation conditions (stuck phase, conflicting evidence,
    irrecoverable state). Returns None when nothing to escalate.
    """
    if evidence.elapsed_in_phase_seconds > DEFAULT_NO_PROGRESS_TTL_SECONDS:
        return Verdict(
            kind=VerdictKind.ESCALATE,
            reason=(
                f"{evidence.current_phase} exceeded no-progress TTL "
                f"({evidence.elapsed_in_phase_seconds}s > {DEFAULT_NO_PROGRESS_TTL_SECONDS}s)"
            ),
            rule_ids=("coach.core.no-progress-ttl",),
            fix_hint="inspect the run; resume after addressing the stall or cancel it",
        )

    pr = evidence.pr_state
    if evidence.current_phase is Phase.COMPLETE and pr is not None and pr.state != "MERGED":
        return Verdict(
            kind=VerdictKind.ESCALATE,
            reason="issue is COMPLETE but its PR is not MERGED (conflicting evidence)",
            rule_ids=("coach.core.complete-pr-mismatch",),
            fix_hint="reconcile the issue phase with the PR state",
        )

    return None


__all__ = [
    "next_transition",
    "evaluate_evidence",
    "review_phase_output",
    "merge_readiness",
    "escalation_for",
    "DEFAULT_NO_PROGRESS_TTL_SECONDS",
]
