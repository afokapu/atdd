"""The CONDITIONAL MINT (#1670 slice C) — run the edge's gates before signing.

``atdd coach approve`` wrote a token attesting that a human pressed a key. It did
not attest that anything was checked: the command parsed ``FROM->TO``, resolved a
signing key, built a token and wrote it, consulting ``GATE_REGISTRY`` at no point.
The artifact ``ApprovalTokenGateCheck`` later accepts as authorisation was
therefore produced without evaluating a single check that gate would run.

Measured 2026-08-03 on ``#1726``: ``PLANNED``, ``RED``, ``GREEN``, ``SMOKE`` and
``REFACTOR`` were all REFUSED by the template-compliance gate while both of its
``approve`` calls SUCCEEDED, leaving two tokens on the shared Control Root for an
issue that never left ``INIT``. Correctly attributed (#1718), at the right path
(#1376), cryptographically sound — and meaningless. This module is what makes the
mint depend on something being observed.

SCOPED TO ``SMOKE->REFACTOR``, AND THE SCOPE IS THE DESIGN
----------------------------------------------------------
:data:`CONDITIONAL_MINT_EDGES` names one edge. ``registrations.py`` binds
``ApprovalTokenGateCheck`` to all five forward edges and ``SmokeExecutionGateCheck``
to ``SMOKE->REFACTOR`` alone, so that is the only edge whose registry holds a check
the mint can honestly consult. On the other four, everything registered IS the
approval check — a conditional mint there would decide whether to write an approval
by asking whether an approval exists. That is not a smaller version of this
feature; it is signing a receipt for its own existence, the exact defect this
program is named for, wearing the fix's clothes.

The rejected alternative was to implement full-width and report ``NOT_APPLICABLE``
on the four bare edges. It looks more complete and is worse: it ships a mint that
*appears* to certify five transitions while certifying one, which is precisely the
"green that means nothing" this program exists to remove. Narrow and true beats
broad and decorative. What widens it later is more substantive checks on the other
edges — and #1619 first, since a registry populated at one call site means an
autonomous runner can already cross those edges ungated.

WHY NOT ``evaluate_transition_gate``
------------------------------------
Because it proceeds on an empty registry, deliberately — the WMBT D019
migration-safety guarantee, so flipping the gate from advisory to blocking could
not make any existing transition start failing. That is the right answer to *"may
this transition happen"* and the wrong answer to *"may I sign an assertion that it
was checked"*. #1619 makes the difference load-bearing rather than theoretical:
``register_approval_checks()`` has exactly one non-test caller, so every process
that is not ``atdd coach transition`` — this mint among them — sees an EMPTY
registry. Evaluating zero checks must read as ``COULD_NOT_CHECK``, which is
#1632's rule (*a run that evaluated 0 of N must not be readable as one that
evaluated N and found nothing*) applied to the gate's own coverage. So this module
composes :func:`~atdd.coach.gate.decision.run_checks` and
:func:`~atdd.coach.gate.decision.evaluate_gate` itself.

THE FOUR CONDITIONS FROM #1670, AND WHERE EACH LANDS
----------------------------------------------------
1. *Read execution records, not claims.* Satisfied by consuming
   ``SmokeExecutionGateCheck`` rather than reimplementing it: the pytest run
   writes its own attestation into the State Store and no CLI verb can write one.
   Nothing here reads the operator-typed ``.atdd/smoke-evidence/<N>.yaml`` stamp,
   and nothing here reads ``.atdd/baselines/validation/*.yaml`` either — a local
   ``atdd validate`` baseline is a claim by whoever ran it, and #1670's body is
   explicit that a token attesting "the validators ran locally and passed" would
   attest the least trustworthy signal in the system.
2. *Consume the skip count.* :class:`MintCoverage` — how many checks were
   registered, excluded and actually evaluated — and a refusal at zero.
3. *Refuse on FAIL and COULD_NOT_CHECK; PROCEED on NOT_APPLICABLE.* The verdicts
   come from #1719 and ``evaluate_gate`` already partitions them. The
   ``NOT_APPLICABLE`` half is the one that breaks the repo if got wrong: the smoke
   check is opt-in per issue and reports it for every issue declaring no
   ``execution_kind: live_smoke`` acceptance — 787 of 787 work items when the edge
   was enabled. Refusing there strands all of them behind ``--force``.
4. *Refuse on stale evidence, bound to HEAD.* ``SmokeExecutionGateCheck`` already
   binds the evidence it reads to HEAD and refuses with ``smoke_stale_commit``, so
   the mint gets this by consuming it. :func:`resolve_head` closes the one hole
   that consumption leaves — see its docstring. The TOKEN's own post-mint
   staleness (an approval outliving the tree it was granted for) is #1721's
   branch/expiry binding, in flight on another branch; NO SECOND BINDING IS BUILT
   HERE.

PURITY: unlike ``decision.py`` this module is impure by nature — it runs git and
drives a registry of checks that open a store. It is the mint's counterpart to
``command_check.py``, and the pure verdict logic it composes stays in
``decision.py`` where the purity contract holds.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Tuple

from atdd.coach.gate.approval_check import GATE_ID as APPROVAL_GATE_ID
from atdd.coach.gate.decision import (
    GateContext,
    GateOutcome,
    GateVerdict,
    evaluate_gate,
    is_transition_gated,
    run_checks,
)
from atdd.coach.gate.registrations import (
    register_approval_checks,
    register_smoke_execution_check,
)
from atdd.coach.gate.registry import GATE_REGISTRY

logger = logging.getLogger(__name__)

#: The edges whose mint is conditional. ONE, and named explicitly rather than
#: derived from "whichever edge happens to hold a substantive check" — an
#: emergent scope would silently widen the moment anything registered elsewhere,
#: which is the objection the ruling above rests on.
CONDITIONAL_MINT_EDGES: frozenset[Tuple[str, str]] = frozenset({("SMOKE", "REFACTOR")})

#: The registrars ``issue_transition.run()`` calls before applying a transition.
#: The mint calls the SAME pair, so the set it certifies is the set that will
#: actually run — a mint evaluated against a differently-populated registry
#: certifies a gate nobody will execute.
DEFAULT_REGISTRARS: Tuple[Callable[..., None], ...] = (
    register_approval_checks,
    register_smoke_execution_check,
)

_GIT_TIMEOUT_S = 10


def resolve_head(worktree: Path) -> Optional[str]:
    """The commit the approval would be granted for, or ``None``.

    SEPARATE FROM ``SmokeExecutionGateCheck._head_sha`` ON PURPOSE, and the
    difference is a policy one rather than an oversight. That function returns
    ``None`` when git is silent and ``evaluate_smoke_execution`` then disables its
    staleness clause ENTIRELY — deliberate, and its own docstring argues it: *"an
    unresolvable HEAD is an environment fault, and turning it into 'smoke did not
    run' would make the gate unfixable rather than fail-closed."*

    For a GATE that is defensible. For a MINT it means the evidence's binding to
    the tree is silently switched off and a signed authorisation is written
    anyway — "I could not look at whether this evidence is stale" passing as "the
    evidence is current", which is #1670's condition 3 in the place it is easiest
    to miss, because nothing fails and nothing is printed.

    So the mint asks the question itself and refuses on ``None``, and
    ``SmokeExecutionGateCheck`` is left exactly as it is: strictness is added
    where the authorisation is written, not taken out of the transition gate,
    where it would change behaviour repo-wide for every issue in every
    non-git environment.
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(worktree), capture_output=True, text=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug(
            "conditional mint: cannot resolve HEAD",
            extra={"worktree": str(worktree), "error": str(exc)},
        )
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


@dataclass(frozen=True)
class MintCoverage:
    """What the mint evaluated, and what it did not — #1632's rule, applied here.

    A bare "the gates passed" cannot distinguish a mint that ran the edge's checks
    and found them satisfied from one that ran nothing at all. These five numbers
    can, and :meth:`render` puts them where an operator reads them.

    ``verified`` counts only ``PASS``. ``NOT_APPLICABLE`` lands in ``none_owed``
    and never in ``verified``: the check observed successfully and correctly
    concluded it was owed nothing, which is a different fact from an obligation
    having been met. Collapsing them would let a mint that verified nothing
    announce that the gates passed — the vacuous green re-entering through the
    report rather than through the decision.
    """

    registered: int
    excluded: int
    evaluated: int
    verified: int
    none_owed: int

    def render(self) -> str:
        return (
            f"registered for this edge: {self.registered}; "
            f"excluded (the approval check itself): {self.excluded}; "
            f"evaluated: {self.evaluated}; "
            f"verified an obligation: {self.verified}; "
            f"found none owed: {self.none_owed}"
        )


@dataclass(frozen=True)
class MintDecision:
    """Whether the token may be written, and everything needed to say why.

    ``conditional`` records whether this edge was subject to the conditional mint
    at all. A ``proceed=True`` with ``conditional=False`` is an ordinary
    unconditional mint — the four other forward edges, and any repo that has not
    enabled this one — and must not be reported as though gates were run.
    """

    proceed: bool
    conditional: bool
    reason: str
    coverage: Optional[MintCoverage] = None
    outcome: Optional[GateOutcome] = None
    verdict: Optional[GateVerdict] = None

    def render(self) -> str:
        """The operator-facing text, refusals included.

        A refusal an operator cannot act on is only marginally better than the
        vacuous mint it replaces, so every blocking check is enumerated with the
        message it produced, and the two blocking verdicts are kept apart: "your
        smoke did not pass" and "I could not read the store" send the operator to
        different places.
        """
        lines = [self.reason]
        if self.coverage is not None:
            lines.append(f"  gate coverage: {self.coverage.render()}")
        if self.outcome is not None:
            for result in self.outcome.failures:
                lines.append(f"  [FAIL {result.gate_id}] {result.message}")
            for result in self.outcome.unobservable:
                lines.append(f"  [COULD_NOT_CHECK {result.gate_id}] {result.message}")
        return "\n".join(lines)


def _load_config(worktree: Path) -> Mapping:
    """``.atdd/config.yaml`` as a mapping, read where the transition gate reads it.

    ``IssueLifecycle._transition_gate`` loads it relative to its target dir, so
    the mint loads it the same way. Deciding gatedness from a different file than
    the transition will consult would let the mint certify an edge the gate does
    not enforce, or refuse one it does.
    """
    import yaml

    config_file = worktree / ".atdd" / "config.yaml"
    if not config_file.exists():
        return {}
    try:
        return yaml.safe_load(config_file.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(
            "conditional mint: .atdd/config.yaml is unreadable; treating as empty",
            extra={"path": str(config_file), "error": str(exc)},
        )
        return {}


def _unconditional(reason: str) -> MintDecision:
    return MintDecision(proceed=True, conditional=False, reason=reason)


def _refuse(reason: str, *, coverage: Optional[MintCoverage] = None,
            outcome: Optional[GateOutcome] = None,
            verdict: GateVerdict = GateVerdict.COULD_NOT_CHECK) -> MintDecision:
    return MintDecision(
        proceed=False, conditional=True, reason=reason,
        coverage=coverage, outcome=outcome, verdict=verdict,
    )


def decide_mint(
    worktree: Path,
    issue_number: int,
    from_phase: str,
    to_phase: str,
    *,
    registry=None,
    config: Optional[Mapping] = None,
    registrars: Optional[Sequence[Callable[..., None]]] = None,
) -> MintDecision:
    """May a signed approval be written for this transition?

    Args:
        worktree: where the mint was invoked; the base for HEAD, the config and
            the gate context handed to each check.
        issue_number: the issue the approval would authorise.
        from_phase / to_phase: the edge, already upper-cased and parsed.
        registry: the gate registry to consult. Defaults to the shipped
            ``GATE_REGISTRY``, resolved at call time rather than bound as a
            default argument so a test can substitute one.
        config: the repo config deciding which transitions are gated. Read from
            ``worktree`` when not supplied.
        registrars: the registrars to invoke before reading the registry.
            Defaults to :data:`DEFAULT_REGISTRARS`; pass ``()`` to consult a
            registry exactly as given.

    Returns:
        A :class:`MintDecision`. ``proceed=False`` means NO TOKEN MAY BE WRITTEN —
        the caller must return before creating the file, because
        ``ApprovalTokenGateCheck`` reads the filesystem and a written token
        authorises the transition whatever was printed alongside it.
    """
    registry = GATE_REGISTRY if registry is None else registry
    registrars = DEFAULT_REGISTRARS if registrars is None else registrars
    edge = f"{from_phase}->{to_phase}"

    # 1. Is this edge conditional at all? Four of the five forward edges are not,
    #    and behave exactly as they did before this module existed.
    if (from_phase, to_phase) not in CONDITIONAL_MINT_EDGES:
        return _unconditional(
            f"{edge}: minted unconditionally — no substantive gate check is "
            f"registered for this edge, so there is nothing this mint could "
            f"honestly certify beyond the approval itself (#1670 slice C covers "
            f"{', '.join(f'{f}->{t}' for f, t in sorted(CONDITIONAL_MINT_EDGES))})"
        )

    # 2. Does this repo enforce it? An ungated edge consults no check at
    #    transition time — including the approval check — so refusing here would
    #    make the command unusable in every repo that has not opted in, to protect
    #    a gate that will not run. Say what the token does and does not mean
    #    instead; silence is what this program exists to remove.
    config = _load_config(worktree) if config is None else config
    if not is_transition_gated(config, from_phase, to_phase):
        return _unconditional(
            f"{edge}: minted unconditionally — this repo does not gate this "
            f"transition (.atdd/config.yaml gate.transitions), so no check runs "
            f"at transition time and this token certifies only the approval"
        )

    # 3. Populate the registry the way the transition dispatch does (#1619: it is
    #    populated at exactly one call site, so without this the mint would read
    #    an empty registry in every invocation).
    for registrar in registrars:
        registrar(registry)

    # 4. Exclude the approval check from its own precondition. Consulting it would
    #    decide whether to write an approval by asking whether an approval exists.
    registered = registry.checks_for(from_phase, to_phase)
    substantive = [
        check for check in registered
        if getattr(check, "gate_id", None) != APPROVAL_GATE_ID
    ]
    coverage_of = lambda verified, none_owed: MintCoverage(  # noqa: E731
        registered=len(registered),
        excluded=len(registered) - len(substantive),
        evaluated=len(substantive),
        verified=verified,
        none_owed=none_owed,
    )

    if not substantive:
        # #1632's rule: 0 of N evaluated is not N evaluated and nothing found.
        return _refuse(
            f"{edge}: REFUSED — no substantive gate check was evaluated, so "
            f"nothing was observed that a token could attest. {len(registered)} "
            f"check(s) registered, all of them the approval check ({APPROVAL_GATE_ID}) "
            f"this mint produces the artifact for. An empty or approval-only "
            f"registry is an unmade observation, not a clean one — if this is "
            f"unexpected, the registrars run at exactly one call site (#1619).",
            coverage=coverage_of(0, 0),
        )

    # 5. Can the tree the approval is for be named? See resolve_head: this closes
    #    the one hole consuming SmokeExecutionGateCheck leaves open.
    head = resolve_head(worktree)
    if head is None:
        return _refuse(
            f"{edge}: REFUSED — HEAD could not be resolved in {worktree}, so "
            f"whether the evidence is current or stale could not be established. "
            f"The smoke attestation's staleness clause is disabled when HEAD is "
            f"unknown, so proceeding would sign an approval over evidence nothing "
            f"checked against the code being advanced.",
            coverage=coverage_of(0, 0),
        )

    # 6. Run them, fail-closed, and aggregate with the gate's own AND-semantics.
    ctx = GateContext(
        issue_number=issue_number, from_phase=from_phase,
        to_phase=to_phase, worktree=worktree,
    )
    outcome = evaluate_gate(run_checks(substantive, ctx))
    coverage = coverage_of(len(outcome.passed_checks), len(outcome.not_applicable))

    if not outcome.proceed:
        logger.warning(
            "conditional mint refused",
            extra={"issue": issue_number, "transition": edge, "head": head,
                   "failures": len(outcome.failures),
                   "unobservable": len(outcome.unobservable)},
        )
        verdict = (
            GateVerdict.FAIL if outcome.failures else GateVerdict.COULD_NOT_CHECK
        )
        return _refuse(
            f"{edge}: REFUSED for #{issue_number} at {head[:12]} — "
            f"{len(outcome.blockers)} check(s) stand in the way.",
            coverage=coverage, outcome=outcome, verdict=verdict,
        )

    # NOT "the gates passed". A mint whose only check reported NOT_APPLICABLE
    # verified nothing, and must not say otherwise — see MintCoverage.
    return MintDecision(
        proceed=True, conditional=True, coverage=coverage, outcome=outcome,
        verdict=GateVerdict.PASS if outcome.passed_checks else GateVerdict.NOT_APPLICABLE,
        reason=(
            f"{edge}: gates evaluated for #{issue_number} at {head[:12]} — "
            f"{coverage.evaluated} check(s) run, {coverage.verified} verified an "
            f"obligation, {coverage.none_owed} found none owed."
        ),
    )
