"""Persistence layer for the train runner (docs/coach-decomposition.md §4.6).

Child 3 (#890) shipped the *contract surface* — the :class:`PersistenceStore`
``Protocol``, :class:`IssueRecord`, and the :func:`load_conventions` signature.
Child 7 (#894) ships the first concrete implementation:

- :func:`load_conventions` — load + normalize the §4.5 phase machine, freeze it
  into a :class:`~atdd.coach.core.types.Conventions` bundle under a deterministic
  sha256 snapshot hash (§4.4 / §5.3).
- :class:`JsonlPersistenceStore` — the default JSONL-backed store. Durable runs
  live under ``<repo>/.atdd/runtime/runs/<run_id>/`` (§5.1); the train runner is
  the single writer to ``events.jsonl`` (§5.2), which is what makes replay
  deterministic (§6.3).
- ``materialize_evidence`` — the bridge to Coach-core: aggregates the manifest,
  the GitHub adapter (Child 4), the validator reports (Child 3), and filesystem
  artifacts into a frozen :class:`~atdd.coach.core.types.Evidence` snapshot.

Layer discipline (§3.3): this module MAY import ``atdd.coach.core``,
``atdd.integrations.*`` and stdlib; it MUST NOT import ``atdd.cli`` or
``atdd.observer``.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable

import yaml

from atdd.coach.core.types import (
    CheckRun,
    CiState,
    Conventions,
    Evidence,
    IssueType,
    Persona,
    Phase,
    PhaseSpec,
    PrState,
    Review,
    TransitionDecision,
    ValidatorReport,
    Verdict,
    VerdictKind,
)
from atdd.train.events import SCHEMA_VERSION
from atdd.train.types import (
    RunId,
    RunState,
    RunStatus,
    RunSummary,
    TrainEvent,
)

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IssueRecord:
    """Manifest row shape — read/written by persistence (§4.7)."""

    id: str
    slug: str
    issue_number: int
    type: IssueType
    status: Phase
    train: str | None
    created: str
    archived: str | None


@runtime_checkable
class PersistenceStore(Protocol):
    """The bridge between the train runner and durable run state (§4.6).

    The single-writer invariant (only the train-runner layer calls
    :meth:`append_event`) is what makes replay deterministic (§5.2).
    """

    # --- run lifecycle ---
    def create_run(self, issue_number: int, *, conventions: Conventions) -> RunId: ...

    def load_run(self, run_id: RunId) -> RunState: ...

    def list_runs(self, *, status: RunStatus | None = None) -> list[RunSummary]: ...

    # --- events (single-writer: train runner) ---
    def append_event(self, run_id: RunId, event: TrainEvent) -> None: ...

    def replay_events(self, run_id: RunId) -> Iterator[TrainEvent]: ...

    # --- decisions (audit trail for every Coach Verdict) ---
    def append_decision(
        self, run_id: RunId, decision: TransitionDecision, *, evidence_hash: str
    ) -> None: ...

    # --- manifest (issue registry) ---
    def get_issue(self, n: int) -> IssueRecord: ...

    def upsert_issue(self, rec: IssueRecord) -> None: ...

    # --- evidence materialization (THE bridge to Coach-core) ---
    def materialize_evidence(self, issue_number: int) -> Evidence: ...


# --------------------------------------------------------------------------- #
# Conventions snapshot (§4.4 / §5.3)                                           #
# --------------------------------------------------------------------------- #

_PHASE_MACHINE_REL = Path("src/atdd/coach/conventions/phase_machine.convention.yaml")


def _phase_machine_path(repo_root: Path) -> Path:
    """Resolve the canonical phase-machine YAML, preferring the in-repo copy."""
    in_repo = repo_root / _PHASE_MACHINE_REL
    if in_repo.is_file():
        return in_repo
    # Fallback to the installed package (worktree vs wheel parity).
    import atdd

    return Path(atdd.__file__).resolve().parent / "coach" / "conventions" / "phase_machine.convention.yaml"


def _persona(value: str | None) -> Persona | None:
    return Persona(value) if value else None


def _phase_machine_from_data(data: dict) -> dict[Phase, PhaseSpec]:
    machine: dict[Phase, PhaseSpec] = {}
    for name, spec in (data.get("phases") or {}).items():
        phase = Phase(name)
        machine[phase] = PhaseSpec(
            name=phase,
            agent=_persona(spec.get("agent")),
            transitions_to=tuple(Phase(p) for p in spec.get("transitions_to", [])),
            pre_commit_gate=spec.get("pre_commit_gate"),
        )
    return machine


def _normalized_snapshot(phase_machine: dict[Phase, PhaseSpec]) -> str:
    """Deterministic, normalized YAML text for the phase machine.

    The same function feeds both :func:`load_conventions` (to compute the hash)
    and ``create_run`` (to write ``conventions.snapshot.yaml``), so the on-disk
    snapshot and the in-memory ``snapshot_hash`` are always byte-consistent.
    """
    phases: dict[str, dict] = {}
    for phase, spec in phase_machine.items():
        entry: dict = {
            "agent": spec.agent.value if spec.agent else None,
            "transitions_to": [p.value for p in spec.transitions_to],
        }
        if spec.pre_commit_gate:
            entry["pre_commit_gate"] = spec.pre_commit_gate
        phases[phase.value] = entry
    return yaml.safe_dump({"phases": phases}, sort_keys=True, default_flow_style=False)


def _freeze(phase_machine: dict[Phase, PhaseSpec], source: Path) -> Conventions:
    """Normalize + hash a phase machine into a frozen :class:`Conventions`.

    Shared by :func:`load_conventions` (reads source conventions) and
    :func:`load_conventions_for_run` (reads a run's frozen snapshot) so the hash
    is computed identically in both directions.
    """
    snapshot_text = _normalized_snapshot(phase_machine)
    snapshot_hash = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
    return Conventions(
        phase_machine=phase_machine,
        rules={},
        prompt_templates={},
        snapshot_hash=snapshot_hash,
        snapshot_paths=(str(source),),
    )


def load_conventions(repo_root: Path) -> Conventions:
    """Load + normalize the convention YAML, compute the snapshot hash, freeze it.

    Conventions are loaded once per run and frozen for the run's duration; the
    snapshot hash is recorded in the run's first event so replay is deterministic
    (§4.4). Hot-reload mid-run is explicitly unsupported.
    """
    path = _phase_machine_path(repo_root)
    data = yaml.safe_load(path.read_text()) or {}
    return _freeze(_phase_machine_from_data(data), path)


# --------------------------------------------------------------------------- #
# Evidence source (injectable seam; the default consults NO provider)          #
# --------------------------------------------------------------------------- #


class EvidenceSource(Protocol):
    """The provider-supplied slice of evidence ``materialize_evidence`` consumes.

    Returns plain integration data (§4.10); ``materialize_evidence`` maps it onto
    the Coach-core types. Any method may raise; the store degrades gracefully.

    This is a **seam**, not a dependency: an extension may inject a source that
    knows about PRs and CI runs. Core ships :class:`_ProviderAbsentSource`, and the
    phase never comes from here at all — see below.
    """

    def read_phase(self, issue: int) -> str | None: ...

    def read_pr_state(self, issue: int): ...  # -> PrStateData | None

    def read_ci_state(self, issue: int) -> str: ...  # CiState value


class _ProviderAbsentSource:
    """Core's default: it reads nothing, because there is nothing here for it to read.

    This class used to call ``atdd.integrations.github.issue_state.read_phase`` and hand
    ``materialize_evidence`` the live GitHub **label**, which then overruled the phase the store
    held. That is the hot-path read #1400 CORE-033 removes (Y001, invariant I7): the mirror is
    not authoritative, so a gate that lets a label outvote the committed projection is a gate
    that GitHub can be wrong about, that an outage can block, and that a rate limit can make
    non-deterministic.

    ``read_phase`` therefore returns ``None`` — meaning "the provider has no opinion", which is
    the only opinion a mirror is entitled to. The phase is the store's, and the store's alone.
    PR and CI state were already "no data" here (the train runner injects a source that knows
    them), so this class now reports the honest empty answer for all three, and does it without
    a provider, a network call, or a provider-absent error (Y001-UNIT-002).
    """

    def read_phase(self, issue: int) -> str | None:
        return None

    def read_pr_state(self, issue: int):
        return None

    def read_ci_state(self, issue: int) -> str:
        return CiState.NONE.value


def _to_pr_state(data) -> PrState | None:
    if data is None:
        return None
    return PrState(
        number=data.number,
        state=data.state,
        mergeable=data.mergeable,
        merge_state=data.merge_state,
        head_sha=data.head_sha,
        check_runs=tuple(
            CheckRun(name=c.name, conclusion=c.conclusion, workflow_id=c.workflow_id)
            for c in data.check_runs
        ),
        reviews=tuple(
            Review(reviewer=r.reviewer, state=r.state, submitted_at=r.submitted_at)
            for r in data.reviews
        ),
        closes_issues=tuple(data.closes_issues),
    )


# Artifacts that have accumulated by the time a phase is current (§4.2).
_ARTIFACTS_BY_PHASE: dict[Phase, frozenset[str]] = {
    Phase.INIT: frozenset(),
    Phase.PLANNED: frozenset({"PLAN_COMMIT"}),
    Phase.RED: frozenset({"PLAN_COMMIT", "RED_TESTS"}),
    Phase.GREEN: frozenset({"PLAN_COMMIT", "RED_TESTS", "GREEN_IMPL"}),
    Phase.SMOKE: frozenset({"PLAN_COMMIT", "RED_TESTS", "GREEN_IMPL", "SMOKE_VERIFIED"}),
    Phase.REFACTOR: frozenset(
        {"PLAN_COMMIT", "RED_TESTS", "GREEN_IMPL", "SMOKE_VERIFIED", "REFACTORED"}
    ),
    Phase.COMPLETE: frozenset(
        {"PLAN_COMMIT", "RED_TESTS", "GREEN_IMPL", "SMOKE_VERIFIED", "REFACTORED"}
    ),
}

_TYPE_BRANCH_PREFIX: dict[IssueType, str] = {
    IssueType.IMPLEMENTATION: "feat",
    IssueType.FIX: "fix",
    IssueType.CHORE: "chore",
    IssueType.REFACTOR: "refactor",
    IssueType.CLEANUP: "chore",
    IssueType.DOCS: "docs",
}


# --------------------------------------------------------------------------- #
# Decision (de)serialization for decisions.jsonl + RunState.decisions          #
# --------------------------------------------------------------------------- #


def _verdict_to_dict(v: Verdict) -> dict:
    return {
        "kind": v.kind.value,
        "reason": v.reason,
        "rule_ids": list(v.rule_ids),
        "fix_hint": v.fix_hint,
        "retry_after_seconds": v.retry_after_seconds,
    }


def _verdict_from_dict(d: dict) -> Verdict:
    return Verdict(
        kind=VerdictKind(d["kind"]),
        reason=d["reason"],
        rule_ids=tuple(d.get("rule_ids", [])),
        fix_hint=d.get("fix_hint"),
        retry_after_seconds=d.get("retry_after_seconds"),
    )


def _decision_to_dict(d: TransitionDecision) -> dict:
    return {
        "from_phase": d.from_phase.value,
        "to_phase": d.to_phase.value if d.to_phase else None,
        "persona": d.persona.value if d.persona else None,
        "prompt_template_id": d.prompt_template_id,
        "evidence_keys_required": list(d.evidence_keys_required),
        "verdict": _verdict_to_dict(d.verdict),
    }


def _decision_from_dict(d: dict) -> TransitionDecision:
    return TransitionDecision(
        from_phase=Phase(d["from_phase"]),
        to_phase=Phase(d["to_phase"]) if d.get("to_phase") else None,
        persona=Persona(d["persona"]) if d.get("persona") else None,
        prompt_template_id=d.get("prompt_template_id"),
        evidence_keys_required=tuple(d.get("evidence_keys_required", [])),
        verdict=_verdict_from_dict(d["verdict"]),
    )


# --------------------------------------------------------------------------- #
# JsonlPersistenceStore (§4.6 default implementation)                          #
# --------------------------------------------------------------------------- #

_RUNS_REL = Path(".atdd/runtime/runs")


class JsonlPersistenceStore:
    """Filesystem-backed :class:`PersistenceStore` (§4.6, §5.1).

    Runs live under ``<repo_root>/.atdd/runtime/runs/<run_id>/``. Each run dir
    holds ``events.jsonl`` (single-writer append-only), ``decisions.jsonl``,
    ``conventions.snapshot.yaml`` + ``conventions.hash`` (frozen at create), and
    ``status.json`` (last-known phase/seq). Validator reports written by
    ``atdd.validators.emit`` land in ``validator-reports.jsonl`` per §5.1.
    """

    def __init__(
        self,
        repo_root: Path,
        *,
        evidence_source: EvidenceSource | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self._evidence: EvidenceSource = evidence_source or _ProviderAbsentSource()
        self._conventions: Conventions | None = None

    # --- paths ----------------------------------------------------------- #
    def _runs_dir(self) -> Path:
        return self.repo_root / _RUNS_REL

    def _run_dir(self, run_id: RunId) -> Path:
        return self._runs_dir() / str(run_id)

    # --- conventions ----------------------------------------------------- #
    def _active_conventions(self) -> Conventions:
        if self._conventions is None:
            self._conventions = load_conventions(self.repo_root)
        return self._conventions

    # --- run lifecycle --------------------------------------------------- #
    def create_run(self, issue_number: int, *, conventions: Conventions) -> RunId:
        self._conventions = conventions
        initial_phase = self._initial_phase(issue_number)

        run_id = self._mint_run_id(issue_number, conventions)
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        snapshot_text = _normalized_snapshot(conventions.phase_machine)
        (run_dir / "conventions.snapshot.yaml").write_text(snapshot_text, encoding="utf-8")
        (run_dir / "conventions.hash").write_text(conventions.snapshot_hash, encoding="utf-8")

        policy_handle_id = hashlib.sha256(
            f"atdd.coach.core:{conventions.snapshot_hash}".encode("utf-8")
        ).hexdigest()

        self.append_event(
            run_id,
            TrainEvent(
                schema_version=SCHEMA_VERSION,
                ts=self._now(),
                run_id=run_id,
                issue_number=issue_number,
                type="RunStarted",
                payload={
                    "run_id": str(run_id),
                    "issue_number": issue_number,
                    "initial_phase": initial_phase.value,
                    "current_phase": initial_phase.value,
                    "conventions_hash": conventions.snapshot_hash,
                    "conventions_snapshot_ref": str(
                        (run_dir / "conventions.snapshot.yaml").relative_to(self.repo_root)
                    ),
                    "policy_handle_id": policy_handle_id,
                },
                seq=0,  # assigned by append_event
            ),
        )
        return run_id

    def load_run(self, run_id: RunId) -> RunState:
        events = list(self.replay_events(run_id))
        if not events:
            raise KeyError(f"unknown run {run_id!r}")

        started = next((e for e in events if e.type == "RunStarted"), None)
        issue_number = started.issue_number if started else events[0].issue_number
        conventions_hash = (
            started.payload.get("conventions_hash", "") if started else ""
        )
        current_phase = self._reconstruct_phase(events)
        decisions = tuple(self._read_decisions(run_id))
        last_seq = max((e.seq for e in events), default=0)

        return RunState(
            run_id=run_id,
            issue_number=issue_number,
            current_phase=current_phase,
            conventions_hash=conventions_hash,
            decisions=decisions,
            last_event_seq=last_seq,
        )

    def list_runs(self, *, status: RunStatus | None = None) -> list[RunSummary]:
        runs_dir = self._runs_dir()
        if not runs_dir.is_dir():
            return []
        summaries: list[RunSummary] = []
        for run_dir in sorted(runs_dir.iterdir()):
            status_file = run_dir / "status.json"
            if not status_file.is_file():
                continue
            data = json.loads(status_file.read_text())
            summaries.append(
                RunSummary(
                    run_id=RunId(data["run_id"]),
                    issue_number=data["issue_number"],
                    state=data.get("state", "RUNNING"),
                )
            )
        return summaries

    # --- events (single-writer) ----------------------------------------- #
    def append_event(self, run_id: RunId, event: TrainEvent) -> None:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        events_file = run_dir / "events.jsonl"
        seq = self._next_seq(events_file)
        row = {
            "schema_version": event.schema_version or SCHEMA_VERSION,
            "ts": event.ts or self._now(),
            "run_id": str(run_id),
            "issue_number": event.issue_number,
            "type": event.type,
            "payload": event.payload,
            "seq": seq,
        }
        with events_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        self._write_status(run_id, row)

    def replay_events(self, run_id: RunId) -> Iterator[TrainEvent]:
        events_file = self._run_dir(run_id) / "events.jsonl"
        if not events_file.is_file():
            return iter(())
        events: list[TrainEvent] = []
        for line in events_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            events.append(
                TrainEvent(
                    schema_version=row["schema_version"],
                    ts=row["ts"],
                    run_id=RunId(row["run_id"]),
                    issue_number=row["issue_number"],
                    type=row["type"],
                    payload=row["payload"],
                    seq=row["seq"],
                )
            )
        events.sort(key=lambda e: e.seq)
        return iter(events)

    # --- decisions ------------------------------------------------------- #
    def append_decision(
        self, run_id: RunId, decision: TransitionDecision, *, evidence_hash: str
    ) -> None:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        row = {"evidence_hash": evidence_hash, "decision": _decision_to_dict(decision)}
        with (run_dir / "decisions.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def _read_decisions(self, run_id: RunId) -> Iterator[TransitionDecision]:
        decisions_file = self._run_dir(run_id) / "decisions.jsonl"
        if not decisions_file.is_file():
            return iter(())
        out: list[TransitionDecision] = []
        for line in decisions_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(_decision_from_dict(json.loads(line)["decision"]))
        return iter(out)

    # --- work items (State Store) ---------------------------------------- #
    def get_issue(self, n: int) -> IssueRecord:
        """Read issue #*n*'s record from the State Store (#1270 slice E).

        The manifest ``sessions`` read is retired; the store is the sole source
        (authoritative since #1203). ``issue_number`` is folded back in from the
        GitHub external-ref (store ``data`` bags do not carry it), so the record
        reconstructs fully. Raises ``KeyError`` when the issue is unregistered.
        """
        from atdd.state.work_item_reader import WorkItemReader

        with WorkItemReader(control_root=self.repo_root) as reader:
            entry = reader.session_entry(n)
        if entry is None:
            raise KeyError(f"issue #{n} not in store")
        entry.setdefault("issue_number", n)
        return self._record_from_session(entry)

    def upsert_issue(self, rec: IssueRecord) -> None:
        """Write the issue record to the **State Store** (#1400 CORE-034, Y002).

        This wrote ``.atdd/manifest.yaml`` — read-modify-write over the very file
        :meth:`get_issue` stopped reading in #1203. A writer whose write nobody reads is not a
        fallback, it is drift with a schedule: the manifest and the store diverge quietly until
        someone reads the wrong one. So the write goes where the read goes.

        The store keys a work item by its slug and carries the GitHub issue number as an
        ``external_ref`` — the same shape :mod:`atdd.state.manifest_import` established, and the
        one :meth:`get_issue` resolves through. Extra keys an existing object carries (``wagon``,
        ``feature``, …) are preserved, exactly as the manifest merge preserved them.
        """
        from atdd.state.db import connect, init_state_store
        from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
        from atdd.state.store import StateStore

        conn = connect(init_state_store(start=self.repo_root))
        try:
            store = StateStore(conn)
            ref = store.external_refs.resolve(GITHUB_PROVIDER, "issue", str(rec.issue_number))
            uid = ref.object_uid if ref is not None else rec.slug
            existing = store.objects.get(uid)
            data = dict(existing.data) if existing is not None else {}
            data.update({
                "id": rec.id,
                "type": rec.type.value,
                "train": rec.train,
                "created": rec.created,
                "archived": rec.archived,
            })
            store.objects.upsert(uid, WORK_ITEM_KIND, state=rec.status.value, data=data)
            if ref is None:
                store.external_refs.link(
                    uid, GITHUB_PROVIDER, "issue", str(rec.issue_number),
                    data={"source": "train-persistence"},
                )
        finally:
            conn.close()
        _log.info(
            "issue record upserted into the State Store",
            extra={"issue": rec.issue_number, "slug": rec.slug, "phase": rec.status.value},
        )

    # --- evidence materialization (THE bridge to Coach-core) ------------- #
    def materialize_evidence(self, issue_number: int) -> Evidence:
        rec = self.get_issue(issue_number)
        conventions = self._active_conventions()

        # The phase is the STORE's, and the store's alone (#1400 CORE-033, I7). It used to be
        # overruled here by the live GitHub label, which made a lifecycle decision depend on a
        # mirror that the spec says is non-authoritative. The provider is asked for PR and CI
        # state — data it genuinely owns — and for nothing that decides a phase.
        current_phase = rec.status
        ci_state = CiState.NONE
        pr_state: PrState | None = None
        try:
            ci_state = CiState(self._evidence.read_ci_state(issue_number))
            pr_state = _to_pr_state(self._evidence.read_pr_state(issue_number))
        except Exception as exc:  # §7.1: a provider that is down degrades; it never propagates.
            _log.warning(
                "materialize_evidence: the evidence source is unavailable; degrading",
                extra={"issue": issue_number, "error": str(exc)},
            )
            ci_state = CiState.NONE
            pr_state = None

        prefix = _TYPE_BRANCH_PREFIX.get(rec.type, "feat")
        return Evidence(
            issue_number=issue_number,
            issue_type=rec.type,
            current_phase=current_phase,
            train_id=rec.train,
            branch=f"{prefix}/{rec.slug}",
            wmbts=(),
            validator_reports=self._read_validator_reports(issue_number),
            ci_state=ci_state,
            pr_state=pr_state,
            last_commit_sha="",
            artifacts_present=_ARTIFACTS_BY_PHASE.get(current_phase, frozenset()),
            elapsed_in_phase_seconds=0,
            conventions_hash=conventions.snapshot_hash,
        )

    # --- internals ------------------------------------------------------- #
    def _now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _next_seq(self, events_file: Path) -> int:
        if not events_file.is_file():
            return 1
        existing = sum(1 for line in events_file.read_text().splitlines() if line.strip())
        return existing + 1

    def _mint_run_id(self, issue_number: int, conventions: Conventions) -> RunId:
        ymd = datetime.now(timezone.utc).strftime("%Y%m%d")
        base = f"run-{issue_number}-{ymd}"
        counter = 0
        while True:
            suffix = hashlib.sha256(
                f"{base}:{conventions.snapshot_hash}:{counter}".encode("utf-8")
            ).hexdigest()[:8]
            run_id = RunId(f"{base}-{suffix}")
            if not self._run_dir(run_id).exists():
                return run_id
            counter += 1

    def _write_status(self, run_id: RunId, row: dict) -> None:
        status_file = self._run_dir(run_id) / "status.json"
        current: dict = {}
        if status_file.is_file():
            current = json.loads(status_file.read_text())
        phase = self._phase_from_event(row) or current.get("current_phase")
        current.update(
            {
                "run_id": str(run_id),
                "issue_number": row["issue_number"],
                "current_phase": phase,
                "state": current.get("state", "RUNNING"),
                "last_event_seq": row["seq"],
                "last_event_at": row["ts"],
            }
        )
        if "started_at" not in current:
            current["started_at"] = row["ts"]
        status_file.write_text(json.dumps(current, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _phase_from_event(row: dict) -> str | None:
        payload = row.get("payload") or {}
        if row.get("type") == "PhaseAdvanced":
            return payload.get("to_phase")
        if row.get("type") in ("RunStarted", "EvidenceMaterialized"):
            return payload.get("current_phase")
        return None

    def _reconstruct_phase(self, events: list[TrainEvent]) -> Phase:
        phase: Phase | None = None
        for event in events:
            value = self._phase_from_event(
                {"type": event.type, "payload": event.payload}
            )
            if value:
                phase = Phase(value)
        return phase or Phase.INIT

    def _initial_phase(self, issue_number: int) -> Phase:
        try:
            return self.get_issue(issue_number).status
        except KeyError:
            # Issue not yet in the manifest — seed a fresh run at INIT, but make
            # the fallback observable rather than silently assuming success.
            _log.info(
                "create_run: issue absent from manifest; seeding run at INIT",
                extra={"issue": issue_number},
            )
            return Phase.INIT

    def _latest_run_dir_for_issue(self, issue_number: int) -> Path | None:
        runs_dir = self._runs_dir()
        if not runs_dir.is_dir():
            return None
        candidates: list[tuple[str, Path]] = []
        for run_dir in runs_dir.iterdir():
            status_file = run_dir / "status.json"
            if not status_file.is_file():
                continue
            try:
                data = json.loads(status_file.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("issue_number") == issue_number:
                candidates.append((data.get("started_at", ""), run_dir))
        if not candidates:
            return None
        candidates.sort(key=lambda t: t[0])
        return candidates[-1][1]

    def _read_validator_reports(self, issue_number: int) -> tuple[ValidatorReport, ...]:
        run_dir = self._latest_run_dir_for_issue(issue_number)
        if run_dir is None:
            return ()
        reports_file = run_dir / "validator-reports.jsonl"
        if not reports_file.is_file():
            return ()
        out: list[ValidatorReport] = []
        for line in reports_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.append(
                ValidatorReport(
                    validator_id=d["validator_id"],
                    rule_id=d["rule_id"],
                    severity=d["severity"],
                    disposition=d["disposition"],
                    unsuppressed_count=d["unsuppressed_count"],
                    location=d.get("location"),
                    detail=d.get("detail"),
                    fix_hint_ref=d.get("fix_hint_ref"),
                )
            )
        return tuple(out)

    # --- issue-record helpers -------------------------------------------- #
    @staticmethod
    def _record_from_session(session: dict) -> IssueRecord:
        return IssueRecord(
            id=str(session.get("id", session.get("issue_number", ""))),
            slug=session.get("slug", ""),
            issue_number=session["issue_number"],
            type=IssueType(session.get("type", "implementation")),
            status=Phase(session.get("status", "INIT")),
            train=session.get("train"),
            created=session.get("created", ""),
            archived=session.get("archived"),
        )


def load_conventions_for_run(run_dir: Path) -> Conventions:
    """Load the FROZEN conventions snapshot for an in-flight run (§5.3 / §6.3).

    Resume reads the snapshot from disk; it does NOT re-read source conventions
    (which may have changed since the run started). This guarantees replay
    determinism.
    """
    snapshot = run_dir / "conventions.snapshot.yaml"
    data = yaml.safe_load(snapshot.read_text()) or {}
    return _freeze(_phase_machine_from_data(data), snapshot)


__all__ = [
    "PersistenceStore",
    "JsonlPersistenceStore",
    "IssueRecord",
    "GitHubEvidenceSource",
    "load_conventions",
    "load_conventions_for_run",
]
