"""SmokeExecutionGateCheck (#1602) — evidence-gated ``SMOKE->REFACTOR``.

The transition out of SMOKE was evidence-blind with respect to the one thing
SMOKE means. Four candidate gates were checked and none of them asked whether a
live-smoke test had executed: ``auto_phase`` is a dict lookup; the
merge-authority ``legal-transition`` check derives its ``smoke_evidence_artifact``
token from *filenames* in the diff; ``IssueManager._gate_smoke_evidence`` is the
#358 presentation ratchet, which fails open four ways and accepts a stamp an
operator can type; and the ``coach.lifecycle.no-green-to-refactor-without-smoke``
node whose ``rule_id`` this check carries was ``documentation-only``.

This check asks the question directly, of the only artifact that can answer it:
the smoke-execution attestation written BY the pytest run itself
(:mod:`atdd.tester.substrate.smoke_attestation` →
:mod:`atdd.state.evidence`). It passes iff that record shows a live-smoke test
that ran, passed, took non-zero time, and did so at the current HEAD.

DELIBERATELY NOT READ — ``.atdd/smoke-evidence/<N>.yaml``. That is the #358
operator-typed stamp, produced by ``atdd validate coder --smoke-required``, a
command that runs no test. Reading it would re-import the exact bug class this
gate exists to close, so the execution attestation lives somewhere else entirely
(the State Store's append-only event log) and this check never looks at the
stamp. ``test_operator_typed_stamp_is_not_accepted_as_execution_evidence``
holds that line.

OPT-IN, PER ISSUE. The check first asks whether THIS issue's own plan scope
declares an ``execution_kind: live_smoke`` acceptance
(:func:`~atdd.coach.gate.smoke_obligation.live_smoke_obligation`). If it declares
none the transition is *not applicable* and passes; only an issue that promised a
live-smoke run is held to one. That ordering is the whole safety property of
enabling this gate: fail-closed on an issue that owes nothing is an obligation it
cannot discharge, and its only exit is ``--force`` — a gate reachable only by
forcing past it is a rubber stamp. Note which question is asked: *this issue's*
obligation, never *the repo's*. ``plan_declares_live_smoke`` answers the
repo-level one and became ``True`` for this repo when E069 landed; consulting it
here would re-gate every issue on the commit that made the gate satisfiable.

FAIL-CLOSED, at three levels, once the obligation exists: the verdict rejects
every degenerate record shape (see
:func:`~atdd.state.evidence.evaluate_smoke_execution`); an unresolvable work item
or unreachable store returns ``passed=False`` here with a message naming the
fault; and anything that raises is converted to a FAIL one level up by
``decision.run_checks``. This check therefore never has to catch to be safe — it
catches only to say something useful.

ISSUE NUMBER -> UID. The gate is handed a provider-side issue number and the
attestation is keyed by work-item uid, so the translation happens HERE, in the
coach layer, through the ``external_refs`` projection. It deliberately does not
happen in :mod:`atdd.state.evidence`, which may not consult ``external_refs``
for a lifecycle decision (I7, spec §8.2 rule 5).
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from atdd.coach.gate.decision import GateCheckResult, GateContext
from atdd.coach.gate.smoke_obligation import SmokeObligation, live_smoke_obligation

logger = logging.getLogger(__name__)

GATE_ID = "smoke-execution"
RULE_ID = "coach.lifecycle.no-green-to-refactor-without-smoke"

#: ``external_refs`` coordinates of the GitHub issue projection (#1183) — the
#: same pair :class:`~atdd.state.work_item_reader.WorkItemReader` resolves by.
_GITHUB_PROVIDER = "github"
_ISSUE_REF_KIND = "issue"

_GIT_TIMEOUT_S = 10


def _head_sha(worktree: Path) -> Optional[str]:
    """The commit the transition would advance, or ``None`` when git is silent.

    ``None`` relaxes only the staleness clause of the verdict (see
    :func:`~atdd.state.evidence.evaluate_smoke_execution`); the execution clauses
    still have to hold, so an unresolvable HEAD can never turn into a pass.
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(worktree), capture_output=True, text=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        logger.debug(
            "smoke-execution gate: cannot resolve HEAD; staleness will not be checked",
            extra={"worktree": str(worktree), "error": str(exc)},
        )
        return None
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def resolve_work_item_uid(store, issue_number: int) -> Optional[str]:
    """The work-item uid an issue number projects onto, or ``None``."""
    ref = store.external_refs.resolve(_GITHUB_PROVIDER, _ISSUE_REF_KIND, str(issue_number))
    return ref.object_uid if ref is not None else None


def work_item_data(store, uid: str) -> dict:
    """The stored work item's ``data`` bag — where its plan scope is recorded.

    Empty for an object the store has no body for, which reads downstream as "no
    plan scope declared" and therefore no obligation. That is the same answer the
    overwhelming majority of issues get, so the degenerate case needs no special
    branch.
    """
    obj = store.objects.get(uid)
    data = getattr(obj, "data", None)
    return dict(data) if isinstance(data, dict) else {}


@dataclass(frozen=True)
class SmokeExecutionGateCheck:
    """Passes iff the State Store records a live-smoke test that actually ran."""

    gate_id: str = GATE_ID
    rule_id: str = RULE_ID

    def run(self, ctx: GateContext) -> GateCheckResult:
        from atdd.state.smoke_evidence import (
            evaluate_smoke_execution,
            open_state_store,
            smoke_executions,
        )

        transition = f"{ctx.from_phase.upper()}->{ctx.to_phase.upper()}"
        produce = (
            f"smoke must actually execute: run the live-smoke suite for "
            f"#{ctx.issue_number} in this worktree — the run itself records the "
            f"attestation (there is no command that writes one)"
        )

        with open_state_store(control_root=ctx.worktree) as store:
            uid = resolve_work_item_uid(store, ctx.issue_number)
            if uid is None:
                return GateCheckResult(
                    self.gate_id, self.rule_id, False,
                    f"#{ctx.issue_number} resolves to no work item in the State Store, "
                    f"so no smoke-execution attestation can be found for it "
                    f"(fail-closed); {produce}",
                )
            obligation = live_smoke_obligation(ctx.worktree, work_item_data(store, uid))
            if not obligation:
                return self._not_applicable(ctx, transition, uid, obligation)
            runs = smoke_executions(store, uid)

        owed = ", ".join(obligation.acceptance_urns)
        verdict = evaluate_smoke_execution(runs, head_sha=_head_sha(ctx.worktree))
        if not verdict.satisfied:
            logger.warning(
                "smoke-execution gate refused a transition",
                extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                       "issue": ctx.issue_number, "uid": uid,
                       "clause": verdict.clause, "runs": len(runs),
                       "owed": owed},
            )
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"{transition} refused [{verdict.clause}] for {uid}: "
                f"{verdict.detail}; #{ctx.issue_number} declares live_smoke "
                f"acceptance(s) {owed}, so {produce}",
            )

        return GateCheckResult(
            self.gate_id, self.rule_id, True,
            f"{transition} attested for {uid} (owed: {owed}): {verdict.detail}",
        )

    def _not_applicable(
        self, ctx: GateContext, transition: str, uid: str, obligation: SmokeObligation
    ) -> GateCheckResult:
        """NOT_APPLICABLE for an issue whose plan scope asks for no live-smoke run.

        Separate from the fail-closed body so the two answers cannot be confused
        while reading: this one is reached only when the obligation is genuinely
        empty, and it never consults the attestation store at all.

        THE VERDICT NOW CARRIES THAT SEPARATION (#1719/C013). Until the gate had
        a four-state vocabulary this branch had to return ``passed=True`` — the
        same value the attested body returns — so the distinction the paragraph
        above describes lived only in the prose and in the message string. It is
        in the type now, and the docstring is no longer the thing holding it.

        NOT ``COULD_NOT_CHECK``, and the difference matters here specifically.
        This branch observed successfully: it resolved the work item, read its
        plan scope, and correctly concluded that nothing in it asks for a live
        smoke run. That is "I looked, and there is no obligation", not "I could
        not look". Returning the blocking verdict here would refuse
        ``SMOKE->REFACTOR`` for essentially every work item in the repo — the
        edge is enabled in ``.atdd/config.yaml`` and this check is registered for
        it — leaving ``--force`` as the routine exit. That is the rubber-stamp
        failure :mod:`~atdd.coach.gate.smoke_obligation` exists to prevent, and
        re-creating it by way of a vocabulary correction would be a worse version
        of the bug being fixed.

        A KNOWN NARROWER GAP, DELIBERATELY LEFT (see #1719's report). When
        ``obligation.scopes`` is empty the work item named no feature and no
        train, so the check did not locate a plan scope to read — arguably a
        genuine could-not-check rather than a not-applicable, and
        :class:`~atdd.coach.gate.smoke_obligation.SmokeObligation` already
        records which case this is. Splitting it here would change the transition
        outcome for every unbound work item, which is a policy decision belonging
        to #1602's owner and to the #1689 backfill, not to this vocabulary
        change. Both cases return NOT_APPLICABLE today, and the message
        distinguishes them for a reader via ``describe_scope()``.
        """
        logger.debug(
            "smoke-execution gate: not applicable",
            extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                   "issue": ctx.issue_number, "uid": uid,
                   "scopes": list(obligation.scopes)},
        )
        return GateCheckResult.not_applicable(
            self.gate_id, self.rule_id,
            f"{transition} not applicable: #{ctx.issue_number} ({uid}) declares no "
            f"live_smoke acceptance, so smoke execution is not required for this "
            f"transition ({obligation.describe_scope()})",
        )
