# URN: test:govern-lifecycle:add-lifecycle-parity-and-import-discipline-tests:lifecycle-parity
# Source of truth: docs/coach-decomposition.md §10.1, Appendix B
"""Lifecycle parity test (required-CI from #889 onward, §10.1 / §20.3).

Drives one issue INIT → COMPLETE + merged PR with every external system mocked,
asserting the migration's end-to-end behavior is preserved. The policy authority
under test is the **real** Child-1 ``atdd.coach.core``; the runner / persistence /
GitHub / agent are dry-run doubles (``tests.fixtures``) standing in for layers
that later children extract (see ``tests/fixtures/__init__.py``).

Faithful to Appendix B with the spec's "the example is illustrative" latitude
(§19.5): the imports point at the Child-2 harness doubles rather than the not-yet
-existent ``atdd.train.runners.jsonl`` / ``atdd.train.persistence``, and
``PolicyHandle`` comes from the harness (it physically lands in ``atdd.train`` in
Child 8, §4.7). The asserted lifecycle + board-sync + replay-determinism
contract is exactly §10.1.

When Child 7/8 land the real ``InMemoryPersistenceStore`` / ``JsonlTrainRunner``,
this test re-points its imports at them; the assertions do not change.
"""
from __future__ import annotations

import pytest

from atdd.coach import core as coach_core
from atdd.coach.core.types import IssueType, Phase, VerdictKind
from tests.fixtures import (
    FakeGitHub,
    InMemoryPersistenceStore,
    LocalDryRunRunner,
    PolicyHandle,
    load_conventions,
)
from tests.fixtures.github import ISSUE_LABEL


def _tick() -> dict:
    """A train-runner event tick (the agent-done signal the loop waits on)."""
    return {"type": "agent_done"}


EXPECTED_PHASES = [
    Phase.PLANNED,
    Phase.RED,
    Phase.GREEN,
    Phase.SMOKE,
    Phase.REFACTOR,
    Phase.COMPLETE,
]


@pytest.mark.parity
def test_full_lifecycle_init_to_complete(tmp_repo, fake_github, fake_agent, fake_observer):
    """Drive one issue INIT → COMPLETE + merged PR with all externals mocked."""
    persistence = InMemoryPersistenceStore()
    conventions = load_conventions(tmp_repo)
    policy = PolicyHandle(coach_module=coach_core, conventions=conventions)
    runner = LocalDryRunRunner(
        persistence=persistence,
        github=fake_github,
        agent=fake_agent,
        observer=fake_observer,
    )

    issue = fake_github.create_issue(slug="parity", type=IssueType.IMPLEMENTATION)
    run_id = runner.start_issue(issue.number, policy=policy)

    # The issue starts at INIT; each tick advances exactly one phase.
    assert runner.status(run_id).current_phase == Phase.INIT
    for expected in EXPECTED_PHASES:
        fake_agent.signal_phase_done(issue.number)
        runner.handle_event(run_id, _tick())
        assert runner.status(run_id).current_phase == expected

    # Merge gate (§10.1): PR merged, label + board both at COMPLETE.
    assert fake_github.pr_for(issue.number).state == "MERGED"
    assert fake_github.issue(issue.number).labels == {ISSUE_LABEL, "atdd:COMPLETE"}
    # Projects v2 Status field synced atomically with the label (closes #882).
    assert fake_github.project_v2_status(issue.number) == "COMPLETE"

    # Architectural assertions (§10.1).
    _assert_event_log_replayable(persistence, run_id)
    _assert_decisions_match_after_replay(persistence, run_id, fake_github)
    _assert_no_coach_core_io_imports()


@pytest.mark.parity
def test_every_decision_is_a_proceed_verdict(tmp_repo, fake_github, fake_agent):
    """The happy path advances on PROCEED verdicts only — no STAY/BLOCKED drift."""
    persistence = InMemoryPersistenceStore()
    policy = PolicyHandle(coach_module=coach_core, conventions=load_conventions(tmp_repo))
    runner = LocalDryRunRunner(persistence=persistence, github=fake_github, agent=fake_agent)

    issue = fake_github.create_issue(slug="parity-verdicts", type=IssueType.IMPLEMENTATION)
    run_id = runner.start_issue(issue.number, policy=policy)
    for _ in EXPECTED_PHASES:
        fake_agent.signal_phase_done(issue.number)
        runner.handle_event(run_id, _tick())

    decisions = persistence.decisions(run_id)
    assert [d.from_phase for d in decisions] == [
        Phase.INIT, Phase.PLANNED, Phase.RED, Phase.GREEN, Phase.SMOKE, Phase.REFACTOR
    ]
    assert [d.to_phase for d in decisions] == EXPECTED_PHASES
    assert all(d.verdict.kind is VerdictKind.PROCEED for d in decisions)


# --------------------------------------------------------------------------- #
# Architectural assertion helpers (§10.1 named asserts)                        #
# --------------------------------------------------------------------------- #


def _assert_event_log_replayable(persistence: InMemoryPersistenceStore, run_id: str) -> None:
    """The event log replays into an equivalent store with monotonic seqs."""
    events = persistence.replay_events(run_id)
    assert events, "no events recorded for run"
    assert [e.seq for e in events] == list(range(1, len(events) + 1)), "event seqs not monotonic"
    assert events[0].type == "RunStarted"
    assert any(e.type == "PhaseAdvanced" for e in events)
    assert any(e.type == "PrMerged" for e in events)
    # Rebuilding from the stream must not raise and must recover the same log.
    rebuilt = InMemoryPersistenceStore.from_events(events)
    assert [e.type for e in rebuilt.replay_events(run_id)] == [e.type for e in events]


def _assert_decisions_match_after_replay(
    persistence: InMemoryPersistenceStore, run_id: str, fake_github: FakeGitHub
) -> None:
    """Replay reproduces identical coach-core decisions (§6.3 determinism)."""
    replay_persistence = InMemoryPersistenceStore.from_events(persistence.replay_events(run_id))
    replay_runner = LocalDryRunRunner(
        persistence=replay_persistence,
        github=fake_github,
        agent=None,  # resume recomputes from the frozen log; no agent needed
    )
    replay_runner.resume(run_id)
    assert persistence.decisions(run_id) == replay_persistence.decisions(run_id)
    assert len(replay_persistence.decisions(run_id)) == len(EXPECTED_PHASES)


def _assert_no_coach_core_io_imports() -> None:
    """coach.core's own module graph imports no forbidden I/O modules.

    (A ``sys.modules`` check is useless under pytest, which itself imports
    subprocess; the import-discipline test owns the fresh-import sanity check.
    Here we statically confirm coach.core's source is I/O-free.)
    """
    import ast
    from pathlib import Path

    import atdd.coach.core as cc

    pkg_dir = Path(cc.__file__).resolve().parent
    forbidden = {"subprocess", "threading", "asyncio", "multiprocessing", "requests", "urllib"}
    for py in pkg_dir.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [n.name for n in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                assert root not in forbidden, f"{py.name} imports forbidden {name!r}"
