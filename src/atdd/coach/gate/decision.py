"""Pure decision logic for the enforcing phase-transition gate (#1020).

This is the keystone the compliance/control program rests on: the advisory gate
(IssueLifecycle._run_gate) ran ``atdd gate`` and discarded the result, so no
per-transition policy could ever block. This module carves the decision —
"given the checks registered for a transition and their results, does the
transition proceed?" — as a PURE unit so it is testable without subprocess, and
IssueLifecycle.transition() becomes a thin caller of it (#958/#1017 register
their real blocking checks INTO the registry rather than forking transition
logic).

PURITY CONTRACT: this module imports stdlib typing primitives ONLY. It MUST NOT
import ``subprocess``, networking, ``gh``/``git``/``cmux``, or any
``atdd.runtime``/``atdd.integrations`` module. The impure, subprocess-backed
reference check lives in ``atdd.coach.gate.command_check``; the registry that
holds checks lives in ``atdd.coach.gate.registry``. Keeping the verdict logic
pure is the compliance bar from the brief (#955/#865), and
``test_c013_unit_004_vocabulary_is_total_and_pure`` now asserts it rather than
leaving this paragraph to hold it alone.

VERDICT VOCABULARY (#1719/C013): a check's answer is a :class:`GateVerdict`, not
a bool. The bool could spell only two of the four facts a check can report, so a
check that could not perform its observation had to borrow ``True`` from the
check that observed nothing wrong — "I could not look" written exactly like "I
looked and it was fine". See :class:`GateVerdict` for the four states and which
of them refuse.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable

# Transitions gated by default when ``.atdd/config.yaml`` says nothing. Ships
# with PLANNED->RED only (scope C). The registry is empty by default, so even a
# gated transition is a no-op until a check is registered — that conjunction is
# the migration-safety guarantee (#1020 scope E, WMBT D019).
DEFAULT_GATED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({("PLANNED", "RED")})


# --------------------------------------------------------------------------- #
# Verdict vocabulary                                                          #
# --------------------------------------------------------------------------- #


class GateVerdict(str, Enum):
    """What a check has to say, in four states rather than two (#1719/C013).

    A ``bool`` can express "observed and satisfied" and "observed and violated".
    It cannot express the other two things a check genuinely reports, so both had
    to be smuggled through ``True``:

    ==================  =========================================  ========
    verdict             means                                      at the gate
    ==================  =========================================  ========
    ``PASS``            it looked, and the rule holds              proceeds
    ``FAIL``            it looked, and the rule is violated        REFUSES
    ``COULD_NOT_CHECK`` it could not perform the observation       REFUSES
    ``NOT_APPLICABLE``  it looked; there is no obligation here     proceeds
    ==================  =========================================  ========

    ``COULD_NOT_CHECK`` refuses because a gate that advances on an unmade
    observation is the defect; a third state that still proceeded would rename it
    rather than fix it. It is reported apart from ``FAIL`` (see
    :class:`GateOutcome`) because the operator's next action differs completely
    between "your code is broken" and "I could not look at your code".

    ``NOT_APPLICABLE`` is the member that carries the risk of re-collapsing the
    distinction, so hold it precisely: the check *did* observe successfully and
    correctly concluded it is owed nothing. That is not "I could not look", and it
    is not ``PASS`` either, because nothing was verified. Keeping it separate is
    what lets a check stop spelling "there was no obligation" as "the obligation
    was met" without changing any transition's outcome.

    NOT AN INVENTION FOR THIS GATE. ``planner.interlocking.route_space`` reached
    the same split independently in its ``NOT_APPLICABLE_BASES`` vocabulary,
    separating ``outcome-cannot-arise`` (this cannot apply) from
    ``not-yet-assessed`` (nobody has looked), and singles the second out as
    ``_TRANSITIONAL`` — a state to be resolved rather than lived in. Different
    domain, unimportable from here by the purity contract above, same shape.

    EXCEPTIONS ARE NOT ``COULD_NOT_CHECK``. :func:`run_checks` converts a raised
    exception to ``FAIL`` and must keep doing so (WMBT E046). A crash is a
    diagnosable fault with a cause; could-not-check is the honest *non-raising*
    branch, where the check ran to completion and had nothing to report on.
    Collapsing them loses the distinction this vocabulary exists to create.
    """

    PASS = "pass"
    FAIL = "fail"
    COULD_NOT_CHECK = "could_not_check"
    NOT_APPLICABLE = "not_applicable"

    @property
    def blocks(self) -> bool:
        """Whether this verdict refuses the transition.

        Stated on the verdict rather than in :func:`evaluate_gate` so a verdict
        added later cannot default to "proceed" by omission — which is precisely
        the silence this vocabulary was introduced to remove.
        """
        return self in _BLOCKING_VERDICTS


#: The verdicts that refuse. Named once, consulted everywhere.
_BLOCKING_VERDICTS: frozenset[GateVerdict] = frozenset(
    {GateVerdict.FAIL, GateVerdict.COULD_NOT_CHECK}
)


# --------------------------------------------------------------------------- #
# Value records                                                               #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GateContext:
    """Everything a gate check is handed about the transition under decision."""

    issue_number: int
    from_phase: str
    to_phase: str
    worktree: Path


@dataclass(frozen=True)
class GateCheckResult:
    """The verdict of a single gate check.

    A check is registered, not hardcoded (scope D): it returns one of these so
    the gate can aggregate verdicts with a bound ``rule_id`` and a human message.

    Prefer the four constructors — :meth:`passing`, :meth:`failing`,
    :meth:`could_not_check`, :meth:`not_applicable` — over the raw initialiser.
    They are the only way to reach the two verdicts a bool cannot spell, and they
    keep a caller from having to reason about ``passed`` at all.

    ``passed`` IS RETAINED, AND MEANS "THIS CHECK DOES NOT OBJECT" (#1719/C013).
    Every pre-existing call site passes it positionally and every pre-existing
    reader consults it, so removing it would have rippled into checks other
    workers hold open. It is derived from the verdict and stays exactly congruent
    with the old two-state behaviour: ``True`` for ``PASS`` and
    ``NOT_APPLICABLE``, ``False`` for ``FAIL`` and ``COULD_NOT_CHECK``. Construct
    with a bare bool and you get the verdict it always meant — ``PASS`` or
    ``FAIL``. What it can no longer do is tell you *which* of the two facts on
    each side you are holding; ``verdict`` is where that now lives.

    A construction whose explicit ``verdict`` contradicts its ``passed`` is
    REFUSED rather than reconciled. Silently picking a winner between two
    representations of one fact is how they drift apart unnoticed, which is the
    defect class this record was changed to close.
    """

    gate_id: str
    rule_id: str
    passed: bool
    message: str
    verdict: Optional[GateVerdict] = None

    def __post_init__(self) -> None:
        if self.verdict is None:
            derived = GateVerdict.FAIL if not self.passed else GateVerdict.PASS
            object.__setattr__(self, "verdict", derived)
            return

        if self.passed == self.verdict.blocks:
            raise ValueError(
                f"gate check {self.gate_id!r} was constructed with passed="
                f"{self.passed} and verdict={self.verdict.value!r}, which "
                f"contradict each other ({self.verdict.value!r} "
                f"{'blocks' if self.verdict.blocks else 'proceeds'}). Use "
                f"GateCheckResult.passing/failing/could_not_check/not_applicable "
                f"so the two cannot disagree."
            )

    # -- constructors, one per verdict -------------------------------------- #
    @classmethod
    def passing(cls, gate_id: str, rule_id: str, message: str) -> "GateCheckResult":
        """It looked, and the rule holds."""
        return cls(gate_id, rule_id, True, message, verdict=GateVerdict.PASS)

    @classmethod
    def failing(cls, gate_id: str, rule_id: str, message: str) -> "GateCheckResult":
        """It looked, and the rule is violated."""
        return cls(gate_id, rule_id, False, message, verdict=GateVerdict.FAIL)

    @classmethod
    def could_not_check(cls, gate_id: str, rule_id: str, message: str) -> "GateCheckResult":
        """It could not perform the observation, so the gate must refuse.

        The message should say what could not be observed and, where possible,
        what would make it observable — a refusal an operator cannot act on is
        only marginally better than the vacuous pass it replaces.
        """
        return cls(gate_id, rule_id, False, message, verdict=GateVerdict.COULD_NOT_CHECK)

    @classmethod
    def not_applicable(cls, gate_id: str, rule_id: str, message: str) -> "GateCheckResult":
        """It looked, and there is no obligation here — so the gate proceeds.

        Reserved for a check that established the absence of an obligation. If
        the check could not establish anything, that is
        :meth:`could_not_check`, and the difference is the whole point.
        """
        return cls(gate_id, rule_id, True, message, verdict=GateVerdict.NOT_APPLICABLE)


@dataclass(frozen=True)
class GateOutcome:
    """The aggregated decision for a transition.

    The blocking results are partitioned, not pooled: ``failures`` holds only
    checks that observed a violation, ``unobservable`` only checks that could not
    observe at all. Identical in effect, distinct in reporting — the remedies
    differ. :attr:`blockers` is the union, for a caller that wants to render
    everything standing in the way; use it rather than ``failures`` when counting,
    or a transition blocked solely by an unobservable check reports as blocked by
    nothing.
    """

    proceed: bool
    results: tuple[GateCheckResult, ...] = ()
    failures: tuple[GateCheckResult, ...] = ()
    unobservable: tuple[GateCheckResult, ...] = ()

    @property
    def blockers(self) -> tuple[GateCheckResult, ...]:
        """Every result standing in the way, failures first."""
        return self.failures + self.unobservable

    @property
    def passed_checks(self) -> tuple[GateCheckResult, ...]:
        """Results that verified something — ``NOT_APPLICABLE`` is not among them."""
        return tuple(r for r in self.results if r.verdict is GateVerdict.PASS)

    @property
    def not_applicable(self) -> tuple[GateCheckResult, ...]:
        """Results that established there was nothing here to verify."""
        return tuple(r for r in self.results if r.verdict is GateVerdict.NOT_APPLICABLE)


@runtime_checkable
class GateCheck(Protocol):
    """The pluggable check contract (scope D).

    A check declares its identity (``gate_id``) and the convention it enforces
    (``rule_id``), and implements ``run`` taking the transition context and
    returning a verdict. #958 registers a structural four-tier check, #1017 an
    approval-token check — both as objects satisfying this Protocol.
    """

    gate_id: str
    rule_id: str

    def run(self, ctx: GateContext) -> GateCheckResult: ...


# --------------------------------------------------------------------------- #
# Pure decision functions                                                     #
# --------------------------------------------------------------------------- #


def evaluate_gate(results: Sequence[GateCheckResult]) -> GateOutcome:
    """Aggregate check results with AND-semantics (WMBT C007, WMBT C013).

    The transition proceeds only when NO result blocks; any blocking result
    refuses, and every one of them is enumerated. No short-circuit, no majority.

    Two verdicts block, and they are partitioned rather than pooled (C013): a
    check that observed a violation lands in ``failures``, a check that could not
    perform its observation lands in ``unobservable``. Before C013 the second was
    not expressible — an unobservable check had to return ``passed=True`` and the
    transition advanced on an observation nobody made. Which bucket a result
    falls into is read off its verdict, never re-derived from ``passed``, so the
    two representations cannot disagree here.
    """
    results_t = tuple(results)
    failures = tuple(r for r in results_t if r.verdict is GateVerdict.FAIL)
    unobservable = tuple(r for r in results_t if r.verdict is GateVerdict.COULD_NOT_CHECK)
    return GateOutcome(
        proceed=not (failures or unobservable),
        results=results_t,
        failures=failures,
        unobservable=unobservable,
    )


def run_checks(checks: Sequence[GateCheck], ctx: GateContext) -> list[GateCheckResult]:
    """Run each check, fail-closed (WMBT E046).

    Any exception a check raises — a missing tool (FileNotFoundError), a timeout
    (subprocess.TimeoutExpired), or anything else — is converted into a FAILING
    result rather than propagated or silently dropped. A check that cannot prove
    it passed is treated as a FAIL, never a silent pass (the advisory
    predecessor's ``return 0``-on-error sin).

    DELIBERATELY NOT ``COULD_NOT_CHECK`` (#1719/C013). A crashed check did fail
    to observe, so routing it to the new verdict reads plausible and is wrong: a
    raised exception is a diagnosable fault carrying a traceback and a cause,
    while could-not-check is the honest *non-raising* branch — the check ran to
    completion and simply had nothing to report on. The verdict is stated
    explicitly below rather than left to derive from ``passed=False``, so this
    boundary is legible at the line that decides it.
    """
    results: list[GateCheckResult] = []
    for check in checks:
        gate_id = getattr(check, "gate_id", check.__class__.__name__)
        rule_id = getattr(check, "rule_id", "")
        try:
            results.append(check.run(ctx))
        except Exception as exc:  # fail-closed — the whole point of this gate
            results.append(
                GateCheckResult.failing(
                    gate_id,
                    rule_id,
                    f"gate check {gate_id} errored (fail-closed): {exc}",
                )
            )
    return results


def is_transition_gated(
    config: Mapping, from_phase: str, to_phase: str
) -> bool:
    """Whether a transition is gated, per ``.atdd/config.yaml`` (scope C).

    Reads the ``gate.transitions`` mapping keyed by ``"FROM->TO"``. An explicit
    entry (True/False) wins; absent that, the built-in
    ``DEFAULT_GATED_TRANSITIONS`` decides (PLANNED->RED is gated by default,
    every other transition is not). An ungated transition never consults a check.
    """
    key = f"{from_phase}->{to_phase}"
    transitions = {}
    if isinstance(config, Mapping):
        gate_cfg = config.get("gate") or {}
        if isinstance(gate_cfg, Mapping):
            transitions = gate_cfg.get("transitions") or {}
    if isinstance(transitions, Mapping) and key in transitions:
        return bool(transitions[key])
    return (from_phase, to_phase) in DEFAULT_GATED_TRANSITIONS


def evaluate_transition_gate(registry, config: Mapping, ctx: GateContext) -> GateOutcome:
    """The single transition-gate decision (the use case).

    Composes config-gating, registry lookup, fail-closed execution and AND-
    aggregation:

    * ungated transition           -> proceed (no check consulted)
    * gated, but no registered check -> proceed (empty-registry no-op; the
      migration-safety default — WMBT D019)
    * gated, with checks            -> run all fail-closed, block if ANY fails
    """
    if not is_transition_gated(config, ctx.from_phase, ctx.to_phase):
        return GateOutcome(proceed=True)

    checks = registry.checks_for(ctx.from_phase, ctx.to_phase)
    if not checks:
        return GateOutcome(proceed=True)

    return evaluate_gate(run_checks(checks, ctx))
