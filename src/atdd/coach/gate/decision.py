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
pure is the compliance bar from the brief (#955/#865).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence, runtime_checkable

# Transitions gated by default when ``.atdd/config.yaml`` says nothing. Ships
# with PLANNED->RED only (scope C). The registry is empty by default, so even a
# gated transition is a no-op until a check is registered — that conjunction is
# the migration-safety guarantee (#1020 scope E, WMBT D019).
DEFAULT_GATED_TRANSITIONS: frozenset[tuple[str, str]] = frozenset({("PLANNED", "RED")})


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
    the gate can aggregate pass/fail with a bound ``rule_id`` and a human message.
    """

    gate_id: str
    rule_id: str
    passed: bool
    message: str


@dataclass(frozen=True)
class GateOutcome:
    """The aggregated decision for a transition."""

    proceed: bool
    results: tuple[GateCheckResult, ...] = ()
    failures: tuple[GateCheckResult, ...] = ()


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
    """Aggregate check results with AND-semantics (WMBT C007).

    The transition proceeds only when EVERY result passed; ANY failure blocks
    and every failing result is enumerated. No short-circuit, no majority.
    """
    results_t = tuple(results)
    failures = tuple(r for r in results_t if not r.passed)
    return GateOutcome(proceed=not failures, results=results_t, failures=failures)


def run_checks(checks: Sequence[GateCheck], ctx: GateContext) -> list[GateCheckResult]:
    """Run each check, fail-closed (WMBT E046).

    Any exception a check raises — a missing tool (FileNotFoundError), a timeout
    (subprocess.TimeoutExpired), or anything else — is converted into a FAILING
    result rather than propagated or silently dropped. A check that cannot prove
    it passed is treated as a FAIL, never a silent pass (the advisory
    predecessor's ``return 0``-on-error sin).
    """
    results: list[GateCheckResult] = []
    for check in checks:
        gate_id = getattr(check, "gate_id", check.__class__.__name__)
        rule_id = getattr(check, "rule_id", "")
        try:
            results.append(check.run(ctx))
        except Exception as exc:  # fail-closed — the whole point of this gate
            results.append(
                GateCheckResult(
                    gate_id=gate_id,
                    rule_id=rule_id,
                    passed=False,
                    message=f"gate check {gate_id} errored (fail-closed): {exc}",
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
