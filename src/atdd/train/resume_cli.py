"""``atdd resume <run_id>`` — replay a crashed train run (Child 9, #896).

The new public CLI surface added by Child 9 (docs/coach-decomposition.md §3.4,
§7.4). It is a thin shell over :meth:`JsonlTrainRunner.resume`: it builds the
JSONL persistence store + runner for the current repo and asks the runner to
replay ``run_id`` per §6.3 (load the frozen conventions snapshot, replay
``events.jsonl`` to reconstruct ``RunState``, re-materialize evidence, recompute
the next decision under the frozen conventions, and append the continuation
events). The drive itself is deterministic and idempotent — resume records the
reconciled decision without advancing the phase label or re-dispatching an agent,
so re-running it never double-executes a phase.

Layer discipline (§3.3): ``atdd.train.*`` MAY import ``atdd.coach.core`` /
``atdd.runtime.*`` / ``atdd.integrations.*`` and stdlib; it MUST NOT import
``atdd.cli`` (cycle) or ``atdd.observer``. ``atdd.cli`` registers the ``resume``
token and forwards argv here — the dependency points inward.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

_log = logging.getLogger("atdd.train.resume")

_DOC_REF = "docs/coach-decomposition.md"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd resume",
        description=(
            "Replay a crashed train run from its durable event log and continue "
            "from where it stopped. Deterministic crash-recovery: given the same "
            "frozen conventions snapshot, event log, and external state, resume "
            f"reproduces identical decisions ({_DOC_REF} §6.3)."
        ),
    )
    parser.add_argument(
        "run_id",
        metavar="RUN_ID",
        help="The run id to resume (e.g. run-816-20260530-a81b0d90).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repo root holding .atdd/runtime/runs/ (defaults to the cwd).",
    )
    return parser


def _latest_decision_event(store, run_id) -> object | None:
    """The most recent ``DecisionMade`` event in the run's log, if any."""
    latest = None
    for event in store.replay_events(run_id):
        if event.type == "DecisionMade":
            latest = event
    return latest


def run(argv: list[str]) -> int:
    """Standalone entry point: parse argv, then resume (used by tests/scripts).

    ``atdd.cli`` declares the ``resume`` args on its own subparser (so the
    top-level ``--help`` renders) and calls :func:`run_args` directly; this argv
    wrapper exists so the command is also runnable in isolation.
    """
    args = _build_parser().parse_args(argv)
    return run_args(run_id=args.run_id, repo_root=args.repo_root)


def run_args(*, run_id: str, repo_root: Path | None = None) -> int:
    """Resume ``run_id`` under ``repo_root`` (defaults to the cwd). Returns an rc."""
    from atdd.train.persistence import JsonlPersistenceStore
    from atdd.train.runners.jsonl import JsonlTrainRunner
    from atdd.train.types import RunId

    repo_root = (repo_root or Path.cwd()).resolve()
    run_id_value = run_id
    run_id = RunId(run_id)

    run_dir = repo_root / ".atdd" / "runtime" / "runs" / str(run_id)
    if not run_dir.is_dir():
        print(
            f"❌ resume: no run {run_id_value!r} under {run_dir.parent} "
            f"(is this the repo root?)",
            file=_stderr(),
        )
        return 1

    store = JsonlPersistenceStore(repo_root)
    runner = JsonlTrainRunner(
        persistence=store, runtime_dir=repo_root / ".atdd" / "runtime"
    )

    try:
        before = store.load_run(run_id)
    except KeyError:
        print(f"❌ resume: run {run_id_value!r} has no event log", file=_stderr())
        return 1

    print(
        f"atdd resume: reconstructed #{before.issue_number} at "
        f"{before.current_phase.value} (last seq {before.last_event_seq})"
    )

    try:
        runner.resume(run_id)
    except RuntimeError as exc:
        # Snapshot drift / non-deterministic replay — surface, don't paper over.
        _log.warning(
            "resume aborted",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
        print(f"❌ resume blocked: {exc}", file=_stderr())
        return 1

    decision_event = _latest_decision_event(store, run_id)
    if decision_event is not None:
        payload = decision_event.payload
        to_phase = payload.get("to_phase") or "(no advance)"
        print(
            f"  recomputed decision: {payload.get('from_phase')} → {to_phase} "
            f"[{payload.get('verdict_kind')}]"
        )
    print(f"  ✔ resumed run {run_id_value}")
    return 0


def _stderr():
    import sys

    return sys.stderr


__all__ = ["run"]
