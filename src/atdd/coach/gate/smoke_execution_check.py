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

FAIL-CLOSED, at three levels: the verdict rejects every degenerate record shape
(see :func:`~atdd.state.evidence.evaluate_smoke_execution`); an unresolvable
work item or unreachable store returns ``passed=False`` here with a message
naming the fault; and anything that raises is converted to a FAIL one level up
by ``decision.run_checks``. This check therefore never has to catch to be safe —
it catches only to say something useful.

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


@dataclass(frozen=True)
class SmokeExecutionGateCheck:
    """Passes iff the State Store records a live-smoke test that actually ran."""

    gate_id: str = GATE_ID
    rule_id: str = RULE_ID

    def run(self, ctx: GateContext) -> GateCheckResult:
        from atdd.state.evidence import (
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
            runs = smoke_executions(store, uid)

        verdict = evaluate_smoke_execution(runs, head_sha=_head_sha(ctx.worktree))
        if not verdict.satisfied:
            logger.warning(
                "smoke-execution gate refused a transition",
                extra={"gate_id": self.gate_id, "rule_id": self.rule_id,
                       "issue": ctx.issue_number, "uid": uid,
                       "clause": verdict.clause, "runs": len(runs)},
            )
            return GateCheckResult(
                self.gate_id, self.rule_id, False,
                f"{transition} refused [{verdict.clause}] for {uid}: "
                f"{verdict.detail}; {produce}",
            )

        return GateCheckResult(
            self.gate_id, self.rule_id, True,
            f"{transition} attested for {uid}: {verdict.detail}",
        )
