"""``LocalDryRunRunner`` — the parity test's TrainRunner stand-in (Child 2).

Drives one issue INIT → COMPLETE by calling the **real** Child-1 coach-core pure
functions (``next_transition`` / ``merge_readiness``) over evidence it
materializes from the in-memory fakes. Every external system is a double:
``FakeGitHub`` for labels/PR/board, ``FakePersistence`` for the event log,
``FakeAgent`` for the done signal. No subprocess, no network, no clock.

This is the "checkpoint between full extraction" runner the spec assigns to
Child 2 (§4.7 implementations table, ``LocalDryRunRunner``). The durable
``JsonlTrainRunner`` ships in Child 8; when it lands, the parity test re-points at
it and this runner is retired. The decision logic here is *only* glue — the
policy authority is entirely coach-core, which is the whole point of the gate.

PURITY NOTE: this module lives under ``tests/`` and is never scanned by the
import-discipline test (which only walks ``src/atdd`` layer dirs), so its use of
fakes does not affect layer rules.
"""
from __future__ import annotations

from dataclasses import dataclass

from atdd.coach import core as coach_core
from atdd.coach.core.types import (
    CiState,
    Evidence,
    IssueType,
    Phase,
    PrState,
    VerdictKind,
)

from .agent import FakeAgent
from .conventions import load_conventions
from .github import FakeGitHub
from .observer import FakeObserver
from .persistence import InMemoryPersistenceStore
from .policy import PolicyHandle


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    issue_number: int
    current_phase: Phase


class MergeBlocked(RuntimeError):
    """Raised if coach-core refuses the merge at the REFACTOR→COMPLETE gate."""


class LocalDryRunRunner:
    def __init__(
        self,
        *,
        persistence: InMemoryPersistenceStore,
        github: FakeGitHub,
        agent: FakeAgent,
        observer: FakeObserver | None = None,
    ) -> None:
        self.persistence = persistence
        self.github = github
        self.agent = agent
        self.observer = observer
        self._conventions = None  # set by start_issue or reloaded by resume

    # --- run lifecycle --------------------------------------------------- #
    def start_issue(self, issue_number: int, *, policy: PolicyHandle) -> str:
        self._conventions = policy.conventions
        run_id = self.persistence.create_run(
            issue_number,
            current_phase=Phase.INIT,
            conventions_hash=policy.conventions.snapshot_hash,
        )
        self.persistence.append_event(
            run_id,
            "RunStarted",
            {
                "run_id": run_id,
                "issue_number": issue_number,
                "initial_phase": Phase.INIT.value,
                "conventions_hash": policy.conventions.snapshot_hash,
                "policy_handle_id": _policy_handle_id(policy),
            },
        )
        # The PR exists for the issue's working life; it is merged at the
        # REFACTOR→COMPLETE gate. Opening it up front keeps merge_readiness's
        # "PR is OPEN" precondition satisfied throughout the drive.
        pr = self.github.open_pr(issue_number)
        self.persistence.append_event(
            run_id, "PrOpened", {"run_id": run_id, "pr_number": pr.number}
        )
        return run_id

    def status(self, run_id: str) -> RunStatus:
        return RunStatus(
            run_id=run_id,
            issue_number=self.persistence.issue_number(run_id),
            current_phase=self.persistence.current_phase(run_id),
        )

    # --- event loop ------------------------------------------------------ #
    def handle_event(self, run_id: str, event: object) -> None:
        """Advance the run one phase in response to an agent-done tick.

        Mirrors the §6.1 loop: materialize evidence → ask coach-core for the
        next transition → on PROCEED, apply the side effects (label/board swap,
        and at the final gate, the PR merge) and record the events.
        """
        issue_number = self.persistence.issue_number(run_id)
        if not self.agent.consume_done(issue_number):
            raise RuntimeError(
                f"handle_event called for #{issue_number} with no pending agent-done signal"
            )

        phase = self.persistence.current_phase(run_id)
        evidence = self._materialize_evidence(run_id, phase)
        self.persistence.append_event(
            run_id, "EvidenceMaterialized", {"run_id": run_id, "current_phase": phase.value}
        )

        decision = coach_core.next_transition(evidence, self._conventions)
        self.persistence.append_decision(run_id, decision)
        self.persistence.append_event(
            run_id,
            "DecisionMade",
            {
                "run_id": run_id,
                "verdict_kind": decision.verdict.kind.value,
                "from_phase": decision.from_phase.value,
                "to_phase": decision.to_phase.value if decision.to_phase else None,
                "persona": decision.persona.value if decision.persona else None,
                "rule_ids": list(decision.verdict.rule_ids),
            },
        )
        if self.observer is not None:
            self.observer.observe({"type": "DecisionMade", "run_id": run_id})

        if decision.verdict.kind is not VerdictKind.PROCEED or decision.to_phase is None:
            return

        to_phase = decision.to_phase
        if to_phase is Phase.COMPLETE:
            self._merge_gate(run_id, evidence, issue_number)

        # Atomic label + Projects v2 sync (closes #882) lives in one call.
        self.github.set_phase(issue_number, to_phase)
        self.persistence.set_current_phase(run_id, to_phase)
        self.persistence.append_event(
            run_id,
            "PhaseAdvanced",
            {"run_id": run_id, "from_phase": phase.value, "to_phase": to_phase.value},
        )

    def _merge_gate(self, run_id: str, evidence: Evidence, issue_number: int) -> None:
        # Evidence here is materialized at REFACTOR (the from_phase), which is
        # the first merge-eligible phase (§4.3 merge_readiness).
        verdict = coach_core.merge_readiness(evidence, self._conventions)
        if not verdict.can_merge:
            raise MergeBlocked(f"merge_readiness blocked: {verdict.blockers}")
        pr = self.github.merge_pr(issue_number)
        self.persistence.append_event(
            run_id, "PrMerged", {"run_id": run_id, "pr_number": pr.number}
        )

    # --- resume / replay determinism ------------------------------------ #
    def resume(self, run_id: str) -> None:
        """Replay the event log, recomputing decisions from frozen evidence.

        Per §6.3 the conventions snapshot — not live source — drives replay;
        here the phase machine is static, so reloading it reproduces the same
        frozen bundle (hash-checked against what the run recorded).
        """
        if self._conventions is None:
            self._conventions = load_conventions()
        recorded_hash = self.persistence.conventions_hash(run_id)
        if self._conventions.snapshot_hash != recorded_hash:
            raise RuntimeError(
                "conventions snapshot drift: replay would not be deterministic"
            )

        for phase in self.persistence.materialized_phases(run_id):
            evidence = self._materialize_evidence(run_id, phase)
            decision = coach_core.next_transition(evidence, self._conventions)
            self.persistence.append_decision(run_id, decision)

    # --- evidence -------------------------------------------------------- #
    def _materialize_evidence(self, run_id: str, phase: Phase) -> Evidence:
        """Build the frozen evidence snapshot coach-core decides on.

        Only ``current_phase`` varies across the happy-path drive; CI is green,
        there are no validator blockers, and artifacts are fixed — so a given
        phase always yields identical evidence, which is what makes replay
        deterministic without re-reading mutated external state.
        """
        issue_number = self.persistence.issue_number(run_id)
        pr = self.github.pr_for(issue_number)
        pr_state = None
        if pr is not None:
            pr_state = PrState(
                number=pr.number,
                state=pr.state,
                mergeable="MERGEABLE",
                merge_state="CLEAN",
                head_sha="0" * 40,
                check_runs=(),
                reviews=(),
                closes_issues=(issue_number,),
            )
        return Evidence(
            issue_number=issue_number,
            issue_type=IssueType.IMPLEMENTATION,
            current_phase=phase,
            train_id="0001-self-compliance-validate",
            branch=f"feat/parity-{issue_number}",
            wmbts=(),
            validator_reports=(),
            ci_state=CiState.SUCCESS,
            pr_state=pr_state,
            last_commit_sha="0" * 40,
            artifacts_present=frozenset(),
            elapsed_in_phase_seconds=0,
            conventions_hash=self._conventions.snapshot_hash,
        )


def _policy_handle_id(policy: PolicyHandle) -> str:
    """Stable id for the policy that produced a run's decisions (§5.2)."""
    import hashlib

    raw = f"{policy.coach_module.__name__}:{policy.conventions.snapshot_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
