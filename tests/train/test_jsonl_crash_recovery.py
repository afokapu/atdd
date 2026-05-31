# URN: test:govern-lifecycle:extract-workflow-wave-runner-and-atdd-resume-cli:E042-SMOKE-001-jsonl-crash-recovery-identical-decisions
# Acceptance: acc:govern-lifecycle:E042-SMOKE-001-jsonl-crash-recovery-identical-decisions
"""§10.3 crash-recovery gate test (docs/coach-decomposition.md §6.3, §10.3, §16 R-7).

This is THE gate that governs any future Temporal adoption: if the JSONL runner
recovers from a mid-wave crash deterministically, Temporal's exactly-once activity
semantics are not justified (§16 R-7). It drives a durable run several phases into
its lifecycle, simulates a ``kill -9`` by discarding the in-memory runner, and
replays the run from disk via :meth:`JsonlTrainRunner.resume` — asserting the
recovered decision is identical and no phase is re-executed.

Hermetic: the GitHub evidence source is a double, so ``materialize_evidence`` is a
pure function of the on-disk manifest + frozen conventions snapshot.
"""
from __future__ import annotations

from pathlib import Path

from atdd.coach import core as coach_core
from atdd.coach.core.types import Phase
from atdd.train.events import SCHEMA_VERSION
from atdd.train.persistence import (
    JsonlPersistenceStore,
    load_conventions,
    load_conventions_for_run,
)
from atdd.train.runner_iface import PolicyHandle
from atdd.train.runners.jsonl import JsonlTrainRunner
from atdd.train.types import RunId, TrainEvent

from tests.coach._e040_helpers import build_temp_repo

ISSUE = 816
# The phases the run was driven through before the crash (3 phases in, §10.3).
_DRIVEN = [
    (Phase.INIT, Phase.PLANNED),
    (Phase.PLANNED, Phase.RED),
    (Phase.RED, Phase.GREEN),
]


class _HermeticGitHub:
    """Deterministic GitHub evidence double — no network, no clock.

    ``read_phase`` returns ``None`` so ``materialize_evidence`` uses the manifest
    status; CI is green so the GREEN gate yields a PROCEED decision.
    """

    def read_phase(self, issue: int):
        return None

    def read_pr_state(self, issue: int):
        return None

    def read_ci_state(self, issue: int) -> str:
        return "success"


def _store(repo_root: Path) -> JsonlPersistenceStore:
    return JsonlPersistenceStore(repo_root, github=_HermeticGitHub())


def _runner(repo_root: Path) -> JsonlTrainRunner:
    return JsonlTrainRunner(
        persistence=_store(repo_root), runtime_dir=repo_root / ".atdd" / "runtime"
    )


def _phase_advanced(store: JsonlPersistenceStore, run_id: RunId, src: Phase, dst: Phase) -> None:
    store.append_event(
        run_id,
        TrainEvent(
            schema_version=SCHEMA_VERSION,
            ts="",
            run_id=run_id,
            issue_number=ISSUE,
            type="PhaseAdvanced",
            payload={"from_phase": src.value, "to_phase": dst.value, "commit_sha": ""},
            seq=0,
        ),
    )


def _count(store: JsonlPersistenceStore, run_id: RunId, etype: str) -> int:
    return sum(1 for e in store.replay_events(run_id) if e.type == etype)


def _drive_three_phases_in(repo_root: Path) -> RunId:
    """Create a durable run and drive it to GREEN via the single-writer log."""
    store = _store(repo_root)
    conventions = load_conventions(repo_root)
    run_id = store.create_run(ISSUE, conventions=conventions)
    for src, dst in _DRIVEN:
        _phase_advanced(store, run_id, src, dst)
    assert store.load_run(run_id).current_phase == Phase.GREEN
    return run_id


def test_kill_mid_wave_then_resume_identical_decisions(tmp_path):
    build_temp_repo(tmp_path, issue_number=ISSUE, status="GREEN")
    PolicyHandle(coach_module=coach_core, conventions=load_conventions(tmp_path))  # constructible

    run_id = _drive_three_phases_in(tmp_path)
    run_dir = tmp_path / ".atdd" / "runtime" / "runs" / str(run_id)

    # The decision the live loop would have computed next, under FROZEN conventions.
    frozen = load_conventions_for_run(run_dir)
    expected = coach_core.next_transition(_store(tmp_path).materialize_evidence(ISSUE), frozen)

    phase_advances_before = _count(_store(tmp_path), run_id, "PhaseAdvanced")
    assert phase_advances_before == len(_DRIVEN)

    # --- kill -9: a brand-new runner (no in-memory state) resumes from disk. ---
    _runner(tmp_path).resume(run_id)

    after = _store(tmp_path).load_run(run_id)
    assert after.decisions[-1] == expected, "resume must reproduce the live loop's decision"
    assert _count(_store(tmp_path), run_id, "RunResumed") == 1
    # No double-execution: resume records the decision but never re-advances a phase.
    assert _count(_store(tmp_path), run_id, "PhaseAdvanced") == phase_advances_before

    # --- resume again on yet another fresh instance → identical decision. ---
    _runner(tmp_path).resume(run_id)
    after2 = _store(tmp_path).load_run(run_id)
    assert after2.decisions[-1] == after2.decisions[-2] == expected
    assert _count(_store(tmp_path), run_id, "PhaseAdvanced") == phase_advances_before


def test_resume_uses_frozen_snapshot_not_live_conventions(tmp_path):
    """Resume must read the run's frozen snapshot, not drifted source conventions.

    Corrupting the in-repo source convention after the run started must not change
    the replay decision (it is computed from the frozen snapshot, §6.3).
    """
    build_temp_repo(tmp_path, issue_number=ISSUE, status="GREEN")
    run_id = _drive_three_phases_in(tmp_path)
    run_dir = tmp_path / ".atdd" / "runtime" / "runs" / str(run_id)
    expected = coach_core.next_transition(
        _store(tmp_path).materialize_evidence(ISSUE), load_conventions_for_run(run_dir)
    )

    # Drift the SOURCE conventions (a new phase machine) — must be ignored on resume.
    src_conv = tmp_path / "src" / "atdd" / "coach" / "conventions" / "phase_machine.convention.yaml"
    src_conv.write_text(src_conv.read_text() + "\n# drift comment — must not affect replay\n")

    _runner(tmp_path).resume(run_id)
    after = _store(tmp_path).load_run(run_id)
    assert after.decisions[-1] == expected
