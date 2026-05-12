"""Reader layer for `atdd coach status` — reads from .atdd/runtime/.

Public surface:
- ``Decision`` — typed wrapper for a coach-decision.schema.json record.
- ``Judgment`` — typed wrapper for a coach-judgment.schema.json record.
- ``AgentState`` — typed wrapper for per-agent heartbeat + context state.
- ``read_decisions(run_id, n, runtime_dir)`` — last N decisions for a run.
- ``read_judgments(n, runtime_dir)`` — last N judgments (unfiltered).
- ``read_agent_state(agent_id, runtime_dir)`` — heartbeat + context for one agent.
- ``find_latest_run_id(runtime_dir)`` — discover the most recent coach_run_id.
- ``list_run_ids(runtime_dir)`` — all unique coach_run_ids from decisions.jsonl.

Design notes:
- All functions are pure reads; no writes, no side effects.
- Missing files / directories are handled gracefully (return empty lists / None).
- Shared by ``run_status`` in coach.py and future tooling.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


@dataclass
class Decision:
    decision_id: str
    timestamp: str
    coach_run_id: str
    issue_number: int
    decision_type: str
    inputs: dict[str, Any]
    outcome: dict[str, Any]
    rationale: Optional[str] = None
    judgment_id: Optional[str] = None


@dataclass
class Judgment:
    judgment_id: str
    timestamp: str
    call_site: str
    inputs_hash: str
    cached: bool
    outcome: str
    model: Optional[str] = None


@dataclass
class AgentState:
    agent_id: str
    issue: Optional[int] = None
    phase: Optional[str] = None
    last_heartbeat: Optional[datetime] = None
    status: str = "unknown"
    token_count: Optional[int] = None


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records


def list_run_ids(runtime_dir: Path) -> list[str]:
    """Return all unique coach_run_id values from decisions.jsonl, in order."""
    records = _read_jsonl(runtime_dir / "coach" / "decisions.jsonl")
    seen: list[str] = []
    seen_set: set[str] = set()
    for r in records:
        rid = r.get("coach_run_id", "")
        if rid and rid not in seen_set:
            seen.append(rid)
            seen_set.add(rid)
    return seen


def find_latest_run_id(runtime_dir: Path) -> Optional[str]:
    """Return the most recent coach_run_id from decisions.jsonl, or None."""
    runs_dir = runtime_dir / "runs"
    if runs_dir.exists():
        subdirs = sorted(
            (d for d in runs_dir.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
        )
        if subdirs:
            return subdirs[-1].name

    run_ids = list_run_ids(runtime_dir)
    return run_ids[-1] if run_ids else None


def read_decisions(
    run_id: str,
    n: int = 10,
    *,
    runtime_dir: Path,
) -> list[Decision]:
    """Return the last ``n`` decisions for ``run_id``."""
    records = _read_jsonl(runtime_dir / "coach" / "decisions.jsonl")
    filtered = [r for r in records if r.get("coach_run_id") == run_id]
    tail = filtered[-n:] if n > 0 else filtered
    return [
        Decision(
            decision_id=r.get("decision_id", ""),
            timestamp=r.get("timestamp", ""),
            coach_run_id=r.get("coach_run_id", ""),
            issue_number=r.get("issue_number", 0),
            decision_type=r.get("decision_type", ""),
            inputs=r.get("inputs", {}),
            outcome=r.get("outcome", {}),
            rationale=r.get("rationale"),
            judgment_id=r.get("judgment_id"),
        )
        for r in tail
    ]


def read_judgments(
    n: int = 5,
    *,
    runtime_dir: Path,
) -> list[Judgment]:
    """Return the last ``n`` judgments (not filtered by run_id)."""
    records = _read_jsonl(runtime_dir / "coach" / "judgments.jsonl")
    tail = records[-n:] if n > 0 else records
    return [
        Judgment(
            judgment_id=r.get("judgment_id", ""),
            timestamp=r.get("timestamp", ""),
            call_site=r.get("call_site", ""),
            inputs_hash=r.get("inputs_hash", ""),
            cached=bool(r.get("cached", False)),
            outcome=str(r.get("outcome", "")),
            model=r.get("model"),
        )
        for r in tail
    ]


def read_agent_state(
    agent_id: str,
    *,
    runtime_dir: Path,
) -> AgentState:
    """Read heartbeat + context for one agent."""
    agent_dir = runtime_dir / "agents" / agent_id
    state = AgentState(agent_id=agent_id)

    heartbeat_path = agent_dir / "heartbeat.json"
    if heartbeat_path.exists():
        try:
            hb = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            observed = hb.get("observed_at", "")
            if observed:
                try:
                    state.last_heartbeat = datetime.fromisoformat(
                        observed.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass
            state.status = hb.get("status", "unknown")
            if "token_count" in hb:
                state.token_count = hb["token_count"]
        except (json.JSONDecodeError, OSError):
            pass

    context_path = agent_dir / "context.json"
    if context_path.exists():
        try:
            ctx = json.loads(context_path.read_text(encoding="utf-8"))
            state.issue = ctx.get("issue")
            state.phase = ctx.get("phase")
        except (json.JSONDecodeError, OSError):
            pass

    return state


def derive_issue_phases(
    run_id: str,
    *,
    runtime_dir: Path,
) -> dict[int, str]:
    """Return the latest phase per issue derived from phase-transition decisions."""
    records = _read_jsonl(runtime_dir / "coach" / "decisions.jsonl")
    phases: dict[int, str] = {}
    for r in records:
        if r.get("coach_run_id") != run_id:
            continue
        if r.get("decision_type") != "phase-transition":
            continue
        issue_num = r.get("issue_number")
        to_phase = r.get("outcome", {}).get("to_phase")
        if issue_num and to_phase:
            phases[int(issue_num)] = to_phase
    return phases
