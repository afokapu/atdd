"""Smoke-execution attestation — the record that a live-smoke test actually ran (#1602).

Split out of :mod:`atdd.state.evidence`, which derives evidence *from a commit*.
This module RECORDS a fact a commit cannot express: that a live-smoke test
executed. The two halves grew into one 700-line file; they are separate domains
with separate readers, so they are separate modules.

The distinction is the whole point of #1602. Before it, every artifact in the
repo that called itself smoke evidence was either a static source scan (#1151's
self-skip validator proves a test *cannot skip*, never that it *ran*) or an
operator-typed stamp (``.atdd/smoke-evidence/<N>.yaml``, produced by ``atdd
validate coder --smoke-required`` — a command that runs no test). Both are
indistinguishable between "smoke ran against real infrastructure" and "somebody
typed a command". An attestation written BY THE RUN, and only by the run, is the
one artifact that tells them apart.

It lives in the State Store's append-only ``events`` log rather than in a file:
a run is an event, there are N of them per work item, and the log already gives
ordering, timestamps and cascade-on-delete for free. There is deliberately no
CLI verb that writes one — the pytest hook in
``atdd.tester.substrate.smoke_attestation`` is the only producer in the tree.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator, List, Mapping, Optional, Sequence

#: ``events.event_type`` for one recorded live-smoke test execution.
SMOKE_EXECUTION_EVENT = "smoke_execution_attested"

#: The one outcome that counts as "smoke executed". ``skipped`` is recorded but
#: never satisfies the gate — a skipped live_smoke test passing vacuously is the
#: #1076 bug (C010-SMOKE-001 "passed" by skipping; run for real it FAILED), and
#: a skip that is merely *absent* from the record is indistinguishable from a run
#: that never happened. So skips are written down, loudly, and rejected.
OUTCOME_PASSED = "passed"

#: Rejection clauses the smoke-execution verdict can carry. Same idea as the
#: ``CLAUSE_*`` vocabulary above: a report that says only "blocked" is useless.
CLAUSE_SMOKE_NOT_ATTESTED = "smoke_not_attested"
CLAUSE_SMOKE_NOT_EXECUTED = "smoke_not_executed"
CLAUSE_SMOKE_ZERO_DURATION = "smoke_zero_duration"
CLAUSE_SMOKE_STALE_COMMIT = "smoke_stale_commit"


class SmokeAttestationError(RuntimeError):
    """The attestation could not be recorded (unknown uid, unwritable store, …).

    Never swallowed into a pass: the producer logs and continues (a pytest hook
    must not break the run it is observing), and the consumer then finds no
    attestation and fails closed. The two halves conspire so that *any* failure
    to record reads as "smoke did not run", never as "smoke ran".
    """


@dataclass(frozen=True)
class SmokeRun:
    """One live-smoke test execution, as recorded by the run itself.

    Every field exists to close a specific past incident:

    ``outcome``
        recorded even when ``skipped``/``failed`` — #1076: absence-of-execution
        was not modelled, so a skip was invisible.
    ``duration_s``
        a "live end-to-end" smoke that returns in 0.12s with no worker running is
        #1192. A zero duration means nothing executed and is rejected below; no
        magic floor above zero is invented here, because the honest detector for
        *fast-but-fake* is E060's constant-evidence rule, not a threshold.
    ``commit_sha`` / ``dirty``
        so an attestation from three commits ago cannot satisfy today's
        transition, and so an attestation captured over uncommitted edits says so
        rather than implying the committed tree was what ran.
    ``execution_kind`` / ``acceptance_urn``
        which planner acceptance this run discharges, so the record is traceable
        back to the claim it supports.
    """

    nodeid: str
    outcome: str
    duration_s: float
    commit_sha: Optional[str] = None
    dirty: bool = False
    execution_kind: Optional[str] = None
    acceptance_urn: Optional[str] = None
    started_at: Optional[str] = None

    @staticmethod
    def from_payload(payload: Mapping[str, Any]) -> "SmokeRun":
        """Rebuild a run from a stored event payload, tolerating drift.

        A payload written by an older/newer producer must not crash the reader —
        a crash here would be converted to a gate FAIL by ``run_checks`` anyway,
        but the operator deserves the surviving records rather than a traceback.
        Unknown keys are dropped; a missing/non-numeric duration reads as 0.0,
        which is exactly the "nothing executed" value the verdict rejects.
        """
        try:
            duration = float(payload.get("duration_s") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        return SmokeRun(
            nodeid=str(payload.get("nodeid") or ""),
            outcome=str(payload.get("outcome") or "").lower(),
            duration_s=duration,
            commit_sha=_opt_str(payload.get("commit_sha")),
            dirty=bool(payload.get("dirty")),
            execution_kind=_opt_str(payload.get("execution_kind")),
            acceptance_urn=_opt_str(payload.get("acceptance_urn")),
            started_at=_opt_str(payload.get("started_at")),
        )


def _opt_str(value: Any) -> Optional[str]:
    return str(value) if isinstance(value, (str, int, float)) and str(value) else None


@dataclass(frozen=True)
class SmokeExecutionVerdict:
    """Whether the recorded runs prove smoke executed — and if not, which clause."""

    satisfied: bool
    clause: Optional[str]
    detail: str


# --------------------------------------------------------------------------- #
# The verdict — PURE over a sequence of runs                                  #
# --------------------------------------------------------------------------- #
def evaluate_smoke_execution(
    runs: Sequence[SmokeRun],
    *,
    head_sha: Optional[str] = None,
) -> SmokeExecutionVerdict:
    """Do these runs prove a live-smoke test executed and passed? (pure)

    Satisfied iff at least ONE run is ``passed`` **and** measured a non-zero
    duration **and** — when ``head_sha`` is supplied — was captured at that
    commit. The clauses are checked in widening order so the message names the
    nearest miss rather than the most generic one: an operator whose only fault
    is a stale attestation should be told to re-run smoke, not told that smoke
    never ran.

    ``head_sha=None`` disables the staleness clause entirely (the caller could
    not determine HEAD). That is the one place this is deliberately permissive:
    an unresolvable HEAD is an environment fault, and turning it into "smoke did
    not run" would make the gate unfixable rather than fail-closed — the
    execution clauses above still have to hold.
    """
    if not runs:
        return SmokeExecutionVerdict(
            False, CLAUSE_SMOKE_NOT_ATTESTED,
            "no smoke-execution attestation is recorded — smoke is not proven to have run",
        )

    passed = [r for r in runs if r.outcome == OUTCOME_PASSED]
    if not passed:
        seen = sorted({r.outcome or "<unrecorded>" for r in runs})
        return SmokeExecutionVerdict(
            False, CLAUSE_SMOKE_NOT_EXECUTED,
            f"{len(runs)} smoke run(s) recorded but none passed (outcomes: {seen}); "
            "a skipped or failing live-smoke test is not executed smoke",
        )

    executed = [r for r in passed if r.duration_s > 0.0]
    if not executed:
        return SmokeExecutionVerdict(
            False, CLAUSE_SMOKE_ZERO_DURATION,
            f"{len(passed)} passing smoke run(s) recorded but every one measured a zero "
            "duration — nothing actually executed",
        )

    if head_sha:
        current = [r for r in executed if r.commit_sha == head_sha]
        if not current:
            stale = sorted({(r.commit_sha or "<unrecorded>")[:12] for r in executed})
            return SmokeExecutionVerdict(
                False, CLAUSE_SMOKE_STALE_COMMIT,
                f"the only passing smoke run(s) were captured at {stale}, not at HEAD "
                f"{head_sha[:12]} — the code that was smoked is not the code being advanced",
            )
        executed = current

    best = max(executed, key=lambda r: r.duration_s)
    where = f" at {best.commit_sha[:12]}" if best.commit_sha else ""
    return SmokeExecutionVerdict(
        True, None,
        f"{len(executed)} passing smoke run(s) recorded{where} "
        f"(e.g. {best.nodeid} in {best.duration_s:.2f}s)",
    )


# --------------------------------------------------------------------------- #
# Store I/O — record and read back, keyed by work-item uid                     #
# --------------------------------------------------------------------------- #
@contextmanager
def open_state_store(
    control_root: Optional[Path] = None,
    *,
    db_path: Optional[Path] = None,
) -> Iterator[Any]:
    """Yield a migrated :class:`~atdd.state.store.StateStore`, closing it after.

    Imported lazily so this module's projection-diff half stays importable with
    no SQLite work done — the merge authority calls it on every commit and must
    not pay to open a store it never reads.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    resolved = init_state_store(start=control_root, db_path=db_path)
    conn = connect(resolved)
    try:
        yield StateStore(conn)
    finally:
        conn.close()


def record_smoke_execution(store: Any, uid: str, run: SmokeRun) -> None:
    """Append one live-smoke execution to ``uid``'s event log.

    Raises :class:`SmokeAttestationError` when the work item is unknown to the
    store (the ``events.object_uid`` foreign key refuses the row) — recording an
    attestation against a uid nothing owns would produce evidence no gate can
    ever find, which is worse than a loud failure.
    """
    payload = {k: v for k, v in asdict(run).items() if v is not None}
    try:
        store.events.append(SMOKE_EXECUTION_EVENT, object_uid=uid, payload=payload)
    except sqlite3.IntegrityError as exc:
        raise SmokeAttestationError(
            f"cannot attest smoke execution for unknown work item {uid!r}: {exc}"
        ) from exc
    except sqlite3.Error as exc:
        raise SmokeAttestationError(
            f"cannot attest smoke execution for {uid!r}: {exc}"
        ) from exc


def smoke_executions(store: Any, uid: str) -> List[SmokeRun]:
    """Every recorded live-smoke execution for ``uid``, in append order."""
    runs: List[SmokeRun] = []
    for event in store.events.list(object_uid=uid):
        if event.event_type != SMOKE_EXECUTION_EVENT:
            continue
        payload = event.payload
        if isinstance(payload, str):  # defensive: a raw row that skipped _loads
            try:
                payload = json.loads(payload)
            except ValueError:
                continue
        if isinstance(payload, Mapping):
            runs.append(SmokeRun.from_payload(payload))
    return runs
