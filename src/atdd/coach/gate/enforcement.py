"""The one seam that binds check REGISTRATION to gate EVALUATION (#1619).

WHY THIS MODULE EXISTS. Before it, ``register_approval_checks`` and
``register_smoke_execution_check`` had exactly ONE non-test call site between
them: ``issue_transition.run``, the ``atdd coach transition`` verb dispatch. So
``GATE_REGISTRY``'s contents depended on HOW a transition was invoked rather than
on WHICH edge was being crossed, and four phase-advancing paths — programmatic
``IssueLifecycle.transition``, the ``issue_reconcile_state`` replay, the
``resume.py`` ``PLANNED_PATH`` walk and ``handlers/watcher.py`` — ran against an
empty registry. The gate did not fail to find a token on those paths. It never
looked.

Registration is bound HERE, to the decision, so no caller can reach a verdict
without it. That is the whole fix: a path that evaluates the gate has, by
construction, registered the checks first.

STILL NOT AN IMPORT-TIME SIDE EFFECT. ``registrations.py`` documents why, and the
reason is unchanged: registering into the module-level ``GATE_REGISTRY`` at import
would pollute it for #1020's migration-safety tests, which assert against the live
registry that pytest collection imports every module into. This module registers
when CALLED. Importing it must leave ``GATE_REGISTRY`` empty, and
``test_r011_unit_001`` probes exactly that in a subprocess.

THE UNREGISTERED-EDGE REFUSAL, AND WHY IT IS NOT IN ``decision.py``. An
unpopulated registry was read as permission to proceed in two places:

  A. ``IssueLifecycle._transition_gate`` returned 0 on ``GATE_REGISTRY.is_empty()``
     — deleted by #1619.
  B. ``decision.evaluate_transition_gate`` returns ``proceed=True`` when
     ``checks_for(from, to)`` is empty — RETAINED, deliberately.

B is a landed acceptance. ``acc:govern-lifecycle:D019-UNIT-002-empty-registry-and-
ungated-transition-proceed`` REQUIRES a gated-but-unregistered edge to proceed
through the pure function, and ``plan/govern_lifecycle/D019.yaml`` states that
conjunction as #1020's migration-safety proof. The pure function cannot tell a
migration-era empty registry from a deleted registrar, because it does not know
whether registration ran. This module does — it performs the registration — so the
refusal belongs here and only here. ``decision.py`` is not touched, and its purity
contract (stdlib typing only) would forbid it importing ``registrations`` anyway.

THE VERDICT IS THE EXISTING ``COULD_NOT_CHECK`` (#1719/C013), not a new refusal
mode. "The registry holds no check for this gated edge" IS an observation that
could not be performed: it already refuses, and it is already reported apart from
``failures`` because the operator's remedy differs — make the gate able to look,
rather than fix the work. A third refusal state would rename the vocabulary C013
was added to complete.
"""
from __future__ import annotations

from typing import Mapping

from atdd.coach.gate.decision import (
    GateCheckResult,
    GateContext,
    GateOutcome,
    evaluate_transition_gate,
    is_transition_gated,
)
from atdd.coach.gate.registry import GATE_REGISTRY

#: Identity of the refusal this module raises on its own behalf. It is not a
#: registered check — it is the report that no registered check exists — so it
#: carries its own gate id rather than borrowing one from a check that is absent.
GATE_ID = "gate-registration"

#: The rule the refusal enforces, in the ``<wagon>.<WMBT>.<name>`` shape the
#: approval check already uses for ``govern-lifecycle.E050.operator-approval-required``.
RULE_ID = "govern-lifecycle.R011.gated-edge-must-have-a-registered-check"


def ensure_gate_checks_registered(registry=GATE_REGISTRY) -> None:
    """Idempotently register every production gate check into ``registry``.

    The single place that knows the full set. Both registrars are idempotent in
    their own right, so calling this on every gate evaluation is cheap and safe.

    Imported inside the function, not at module scope: the check modules pull in
    filesystem and signing machinery, and keeping that off this module's import
    path is what lets ``import atdd.coach.gate.enforcement`` stay free of side
    effects and heavy dependencies alike.
    """
    from atdd.coach.gate.registrations import (
        register_approval_checks,
        register_smoke_execution_check,
    )

    register_approval_checks(registry)
    register_smoke_execution_check(registry)


def enforce_transition_gate(
    config: Mapping, ctx: GateContext, registry=GATE_REGISTRY
) -> GateOutcome:
    """Decide a transition, having first registered the checks it will consult.

    The entry point EVERY phase-advancing path calls. Composes:

    * register (always, idempotently) — so the verdict cannot depend on which
      caller or CLI verb got here first;
    * ungated edge                      -> proceed, no check consulted;
    * gated edge with no check          -> REFUSE as ``COULD_NOT_CHECK``;
    * gated edge with checks            -> delegate to the pure
      ``evaluate_transition_gate``, unchanged.

    The fail-CLOSED half is untouched: a check that errors or times out is still
    converted to a FAIL by ``run_checks``, and #1719's full blocking set is still
    what a caller must render.
    """
    ensure_gate_checks_registered(registry)

    if not is_transition_gated(config, ctx.from_phase, ctx.to_phase):
        return GateOutcome(proceed=True)

    if not registry.checks_for(ctx.from_phase, ctx.to_phase):
        return _unregistered_outcome(ctx)

    return evaluate_transition_gate(registry, config, ctx)


def _unregistered_outcome(ctx: GateContext) -> GateOutcome:
    """The refusal for a gated edge that registration left uncovered.

    Names the edge, and says what would make it observable. A refusal an operator
    cannot act on is only marginally better than the vacuous pass it replaces.
    """
    edge = f"{ctx.from_phase.upper()}->{ctx.to_phase.upper()}"
    result = GateCheckResult.could_not_check(
        GATE_ID,
        RULE_ID,
        (
            f"{edge} is gated, but no gate check is registered for it, so the "
            f"gate cannot look. Either register a check for {edge} (see "
            f"atdd.coach.gate.registrations) or stop gating it in .atdd/config.yaml "
            f"under gate.transitions. Proceeding here would report the transition "
            f"as gated while nothing had been verified."
        ),
    )
    return GateOutcome(
        proceed=False,
        results=(result,),
        unobservable=(result,),
    )
