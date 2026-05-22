"""`atdd agent <subcommand>` — persona-agent runtime CLI (J2, issue #497).

Every persona side-effect (heartbeat, runtime event, structured question,
escalation, done-signal, phase-aware commit, reviewer report) flows through
this module. Writes target `.atdd/runtime/agents/<id>/` per spec §3.2 so
the runtime watcher (#J5) has a deterministic parse target.

Subcommands per spec §5.3:
    heartbeat   — rewrite `heartbeat.json` (single-doc)
    event       — append a record to `events.jsonl` (schema: runtime-event.schema.json)
    commit      — produce a phase-aware git commit with the four spec §7.3 trailers
    ask         — append to `questions.jsonl`; coach answers via `answers/<qid>.json`
    escalate    — append to `escalations.jsonl` with severity tag
    done        — write `done.json` final-summary record
    context     — print phase + WMBT context from spawn-time `context.json` bundle
    review      — reviewer-only: write `reviews/<review-id>.json` (spec §6.3)

Out of scope (each owned by an adjacent track):
- runtime watcher / git watcher / liveness checker (#J5)
- coach-side answer generation (#J3)
- observer correction injection (#L1)
- reviewer no-write spawn adapter (#N1)
- per-LLM convention rendering (#K4)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from atdd.coach.commands import checkpoint as checkpoint_mod

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frozen enums
# ---------------------------------------------------------------------------

# Subset of spec §4.1 phases that agents may use as a commit-time phase
# trailer. INIT/PLANNED/COMPLETE/BLOCKED/MERGED commits are not part of
# the agent surface (per issue body — those transitions are coach-driven).
COMMIT_PHASES: tuple[str, ...] = ("RED", "GREEN", "SMOKE", "REFACTOR")

# `runtime-event.schema.json` enum (frozen at C0). Keep in sync with
# src/atdd/coach/schemas/runtime-event.schema.json.
EVENT_TYPES: frozenset[str] = frozenset({
    "agent_spawned",
    "heartbeat",
    "commit_observed",
    "event_emitted",
    "escalation_emitted",
    "pr_opened",
    "pr_closed",
    "validation_pending",
    "validation_complete",
    "review_complete",
    "correction_emitted",
    "process_silence",
})

QUESTION_TYPES: frozenset[str] = frozenset({"choice", "text", "approval", "confirmation"})
SEVERITIES: frozenset[str] = frozenset({"info", "warn", "block"})


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def _now_iso_z() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _runtime_root(runtime_root: Optional[Path]) -> Path:
    if runtime_root is not None:
        return Path(runtime_root)
    env = os.environ.get("ATDD_RUNTIME_ROOT")
    if env:
        return Path(env)
    return Path.cwd() / ".atdd" / "runtime"


def _agent_dir(agent_id: str, runtime_root: Optional[Path]) -> Path:
    d = _runtime_root(runtime_root) / "agents" / agent_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_agent_id(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    env = os.environ.get("ATDD_AGENT_ID")
    if env:
        return env
    raise ValueError(
        "agent id required (pass --agent-id or set ATDD_AGENT_ID)"
    )


def _resolve_issue(explicit: Optional[int]) -> int:
    if explicit is not None:
        return int(explicit)
    env = os.environ.get("ATDD_ISSUE")
    if env:
        return int(env)
    raise ValueError(
        "issue number required (pass --issue or set ATDD_ISSUE)"
    )


# ---------------------------------------------------------------------------
# Reviewer guard — reject write operations for reviewer persona
# ---------------------------------------------------------------------------


def _read_persona_from_manifest(agent_id: str, runtime_root: Optional[Path]) -> Optional[str]:
    """Read the persona from the agent's manifest.json. Returns None if
    the manifest doesn't exist (backward compatibility with pre-manifest
    spawns)."""
    agent_dir = _runtime_root(runtime_root) / "agents" / agent_id
    manifest = agent_dir / "manifest.json"
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text())
        return data.get("persona")
    except (json.JSONDecodeError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None


def _reject_if_reviewer(agent_id: str, runtime_root: Optional[Path]) -> None:
    """Raise ValueError if the agent is a reviewer persona. Reviewers
    must not commit — their only output channel is ``atdd agent review``
    (spec §6.3 hard rule)."""
    persona = _read_persona_from_manifest(agent_id, runtime_root)
    if persona == "reviewer":
        raise ValueError(
            "Reviewer persona agents cannot commit (spec §6.3 no-write "
            "constraint). Use `atdd agent review --target-commit <sha> "
            "--report-file <path>` as the sole output channel."
        )


# ---------------------------------------------------------------------------
# Atomic writers
# ---------------------------------------------------------------------------


def _write_single_doc(path: Path, payload: dict) -> None:
    """Write `payload` atomically as JSON to `path` (temp+rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True))
        fh.write("\n")


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def cmd_heartbeat(
    *,
    agent_id: Optional[str] = None,
    current_step: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> Path:
    aid = _resolve_agent_id(agent_id)
    payload: dict[str, Any] = {"timestamp": _now_iso_z()}
    if current_step is not None:
        payload["current_step"] = current_step
    target = _agent_dir(aid, runtime_root) / "heartbeat.json"
    _write_single_doc(target, payload)
    return target


def cmd_event(
    event_type: str,
    *,
    agent_id: Optional[str] = None,
    data: Optional[dict] = None,
    runtime_root: Optional[Path] = None,
) -> dict:
    if event_type not in EVENT_TYPES:
        raise ValueError(
            f"event_type {event_type!r} not in runtime-event.schema.json enum"
        )
    aid = _resolve_agent_id(agent_id)
    record: dict[str, Any] = {
        "event_type": event_type,
        "agent_id": aid,
        "timestamp": _now_iso_z(),
        "payload": dict(data or {}),
    }
    target = _agent_dir(aid, runtime_root) / "events.jsonl"
    _append_jsonl(target, record)
    return record


def cmd_ask(
    *,
    question: str,
    type: str,  # noqa: A002 — public CLI surface uses `--type`
    agent_id: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> dict:
    if type not in QUESTION_TYPES:
        raise ValueError(
            f"question type {type!r} not in {sorted(QUESTION_TYPES)}"
        )
    aid = _resolve_agent_id(agent_id)
    record: dict[str, Any] = {
        "question_id": f"q-{uuid.uuid4().hex[:12]}",
        "type": type,
        "question": question,
        "timestamp": _now_iso_z(),
    }
    target = _agent_dir(aid, runtime_root) / "questions.jsonl"
    _append_jsonl(target, record)
    return record


def read_answer(
    *,
    question_id: str,
    agent_id: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> Optional[dict]:
    """Coach writes `.atdd/runtime/agents/<id>/answers/<qid>.json`; this
    helper reads it back for the agent. Returns None if unanswered."""
    aid = _resolve_agent_id(agent_id)
    target = _agent_dir(aid, runtime_root) / "answers" / f"{question_id}.json"
    if not target.is_file():
        return None
    return json.loads(target.read_text())


def cmd_escalate(
    *,
    reason: str,
    severity: str = "info",
    agent_id: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> dict:
    if severity not in SEVERITIES:
        raise ValueError(
            f"severity {severity!r} not in {sorted(SEVERITIES)}"
        )
    aid = _resolve_agent_id(agent_id)
    record: dict[str, Any] = {
        "reason": reason,
        "severity": severity,
        "timestamp": _now_iso_z(),
    }
    target = _agent_dir(aid, runtime_root) / "escalations.jsonl"
    _append_jsonl(target, record)
    return record


def cmd_done(
    *,
    agent_id: Optional[str] = None,
    summary: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> Path:
    aid = _resolve_agent_id(agent_id)
    payload: dict[str, Any] = {"timestamp": _now_iso_z()}
    if summary is not None:
        payload["summary"] = summary
    target = _agent_dir(aid, runtime_root) / "done.json"
    _write_single_doc(target, payload)
    return target


def cmd_context(
    *,
    agent_id: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> dict:
    """Read the spawn-time bundle written by the spawner (#K4)."""
    aid = _resolve_agent_id(agent_id)
    target = _agent_dir(aid, runtime_root) / "context.json"
    if not target.is_file():
        raise FileNotFoundError(
            f"no spawn bundle at {target} — context is written at spawn time"
        )
    return json.loads(target.read_text())


def _require_reviewer_persona(agent_id: str, runtime_root: Optional[Path]) -> None:
    """Raise ValueError unless the agent's persona is 'reviewer'.

    ``atdd agent review`` is the reviewer's sole output channel (spec §6.3);
    non-reviewer callers and agents without a manifest are rejected.
    """
    persona = _read_persona_from_manifest(agent_id, runtime_root)
    if persona != "reviewer":
        raise ValueError(
            f"atdd agent review requires persona=reviewer, got "
            f"persona={persona!r}. Only reviewer agents may submit review "
            f"reports (spec §6.3 persona-bounded write authority)."
        )


def cmd_review(
    *,
    target_commit: str,
    report_file: str,
    agent_id: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> Path:
    """Reviewer-only output channel (spec §6.3 hard rule).

    Reads the report file, validates against ``review-report.schema.json``
    plus the three cross-field hard rules, persists the validated report
    to ``reviews/<review-id>.json``, and emits a ``review_complete`` event.
    On validation failure: raises ValueError with rule-id error, writes
    nothing, emits nothing.
    """
    report_path = Path(report_file)
    if not report_path.is_file():
        raise FileNotFoundError(
            f"report file not found: {report_path}"
        )
    aid = _resolve_agent_id(agent_id)
    _require_reviewer_persona(aid, runtime_root)

    # Parse report JSON
    try:
        report_data = json.loads(report_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"report file is not valid JSON: {report_path}: {exc}"
        ) from exc

    # Validate against schema + hard rules
    from atdd.coach.utils.review_report_intake import validate_review_report
    result = validate_review_report(report_data)
    if not result.valid:
        parts = []
        for err in result.errors:
            parts.append(f"[{err.rule}] {err.message}")
        raise ValueError(
            f"review report validation failed: {'; '.join(parts)}"
        )

    # Persist the validated report using the report's own review_id
    review_id = report_data["review_id"]
    target = _agent_dir(aid, runtime_root) / "reviews" / f"{review_id}.json"
    _write_single_doc(target, report_data)

    # Emit review_complete event per runtime-event.schema.json
    event_record: dict[str, Any] = {
        "event_type": "review_complete",
        "agent_id": aid,
        "timestamp": _now_iso_z(),
        "payload": {
            "review_id": review_id,
            "verdict": report_data["verdict"],
            "phase": report_data["phase"],
            "target_commit": target_commit,
        },
    }
    events_path = _agent_dir(aid, runtime_root) / "events.jsonl"
    _append_jsonl(events_path, event_record)

    return target


# ---------------------------------------------------------------------------
# Commit — phase-aware, four trailers, delegates worker-state to checkpoint
# ---------------------------------------------------------------------------


def _compose_commit_message(
    *,
    message: str,
    agent_id: str,
    issue: int,
    phase: str,
    wmbt_urn: Optional[str],
) -> str:
    """Compose subject + blank + trailer block per git interpret-trailers."""
    trailers = [
        f"Agent-Id: {agent_id}",
        f"Issue: {issue}",
    ]
    if wmbt_urn:
        trailers.append(f"WMBT-Urn: {wmbt_urn}")
    trailers.append(f"Phase: {phase}")
    return f"{message.rstrip()}\n\n" + "\n".join(trailers) + "\n"


def cmd_commit(
    *,
    phase: str,
    message: str,
    agent_id: Optional[str] = None,
    issue: Optional[int] = None,
    wmbt_urn: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> str:
    """Produce a phase-aware git commit and update worker checkpoint.

    Returns the full SHA of the new commit.
    """
    aid = _resolve_agent_id(agent_id)
    _reject_if_reviewer(aid, runtime_root)

    if phase not in COMMIT_PHASES:
        raise ValueError(
            f"phase {phase!r} not in agent commit enum {COMMIT_PHASES} "
            f"(INIT/PLANNED/COMPLETE/BLOCKED/MERGED commits are coach-driven)"
        )
    aid = _resolve_agent_id(agent_id)
    iss = _resolve_issue(issue)

    full_msg = _compose_commit_message(
        message=message,
        agent_id=aid,
        issue=iss,
        phase=phase,
        wmbt_urn=wmbt_urn,
    )
    # Hooks must still run — never pass --no-verify here.
    subprocess.run(
        ["git", "commit", "-m", full_msg],
        check=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    # Delegate worker-state durability to the existing checkpoint primitive
    # (per absorption discipline, spec §0.2).
    checkpoint_mod.write_worker_checkpoint(
        issue=iss,
        phase=phase,
        summary=message,
        open_files=[],
        last_commit=sha,
    )
    return sha


# ---------------------------------------------------------------------------
# Inbox primitive (cli-return.jsonl consume/peek) — #824
# ---------------------------------------------------------------------------

_CLI_RETURN_OFFSET_KEY = ".cli-return-offset"


def _cli_return_path(agent_id: str, runtime_root: Optional[Path]) -> Path:
    return _agent_dir(agent_id, runtime_root) / "cli-return.jsonl"


def _offset_path(agent_id: str, runtime_root: Optional[Path]) -> Path:
    return _agent_dir(agent_id, runtime_root) / ".cli-return-offset"


def _read_consumed_offset(agent_id: str, runtime_root: Optional[Path]) -> int:
    path = _offset_path(agent_id, runtime_root)
    if path.exists():
        try:
            return int(path.read_text().strip())
        except (ValueError, OSError) as e:
            _logger.warning(
                "cli-return offset file unreadable, resetting to 0",
                extra={"path": str(path), "error": str(e)},
            )
    return 0


def _write_consumed_offset(agent_id: str, runtime_root: Optional[Path], offset: int) -> None:
    path = _offset_path(agent_id, runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(str(offset))
    tmp.replace(path)


def _read_entries_from_offset(
    cli_return_path: Path, start_offset: int
) -> tuple[list[dict], int]:
    """Read JSONL entries from start_offset; return (entries, new_offset).

    Skips invalid JSON lines without crashing.
    """
    if not cli_return_path.exists():
        return [], start_offset

    entries: list[dict] = []
    new_offset = start_offset
    with cli_return_path.open("r", encoding="utf-8") as fh:
        fh.seek(start_offset)
        while True:
            line_start = fh.tell()
            line = fh.readline()
            if not line:
                new_offset = fh.tell()
                break
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
                new_offset = fh.tell()
            except json.JSONDecodeError:
                import sys
                print(
                    f"[agent inbox] WARNING: skipping invalid JSON at offset {line_start}",
                    file=sys.stderr,
                )
                new_offset = fh.tell()
    return entries, new_offset


def cmd_inbox_drain(
    *,
    agent_id: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> list[dict]:
    """Read and mark consumed all new cli-return.jsonl entries."""
    aid = _resolve_agent_id(agent_id)
    offset = _read_consumed_offset(aid, runtime_root)
    path = _cli_return_path(aid, runtime_root)

    entries, new_offset = _read_entries_from_offset(path, offset)
    if new_offset != offset:
        _write_consumed_offset(aid, runtime_root, new_offset)
    return entries


def cmd_inbox_peek(
    *,
    agent_id: Optional[str] = None,
    runtime_root: Optional[Path] = None,
) -> list[dict]:
    """Read new cli-return.jsonl entries WITHOUT advancing the consumed offset."""
    aid = _resolve_agent_id(agent_id)
    offset = _read_consumed_offset(aid, runtime_root)
    path = _cli_return_path(aid, runtime_root)

    entries, _ = _read_entries_from_offset(path, offset)
    return entries


# ---------------------------------------------------------------------------
# argparse dispatcher (`atdd agent <subcommand> ...`)
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd agent",
        description=(
            "Persona-agent runtime CLI. Writes every side-effect to "
            "`.atdd/runtime/agents/<id>/` per spec §3.2 so the runtime "
            "watcher (#J5) can parse them deterministically."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # heartbeat
    p_hb = sub.add_parser("heartbeat", help="Update heartbeat.json")
    p_hb.add_argument("--agent-id", default=None, dest="agent_id")
    p_hb.add_argument("--current-step", default=None, dest="current_step")

    # event
    p_ev = sub.add_parser("event", help="Append a record to events.jsonl")
    p_ev.add_argument("event_type", help="Event type from runtime-event.schema.json enum")
    p_ev.add_argument("--agent-id", default=None, dest="agent_id")
    p_ev.add_argument("--data", default=None, help="JSON-encoded payload dict")

    # commit
    p_co = sub.add_parser("commit", help="Phase-aware git commit with the four spec §7.3 trailers")
    p_co.add_argument("--phase", required=True, choices=list(COMMIT_PHASES))
    p_co.add_argument("--message", "-m", required=True)
    p_co.add_argument("--agent-id", default=None, dest="agent_id")
    p_co.add_argument("--issue", type=int, default=None)
    p_co.add_argument("--wmbt-urn", default=None, dest="wmbt_urn")

    # ask
    p_ask = sub.add_parser("ask", help="Append a structured question to questions.jsonl")
    p_ask.add_argument("--question", required=True)
    p_ask.add_argument("--type", required=True, choices=sorted(QUESTION_TYPES))
    p_ask.add_argument("--agent-id", default=None, dest="agent_id")

    # escalate
    p_esc = sub.add_parser("escalate", help="Append to escalations.jsonl")
    p_esc.add_argument("--reason", required=True)
    p_esc.add_argument("--severity", default="info", choices=sorted(SEVERITIES))
    p_esc.add_argument("--agent-id", default=None, dest="agent_id")

    # done
    p_done = sub.add_parser("done", help="Write done.json final-summary record")
    p_done.add_argument("--summary", default=None)
    p_done.add_argument("--agent-id", default=None, dest="agent_id")

    # context
    p_ctx = sub.add_parser("context", help="Print phase + WMBT context from spawn bundle")
    p_ctx.add_argument("--agent-id", default=None, dest="agent_id")

    # review (reviewer-only output channel — spec §6.3)
    p_rv = sub.add_parser("review", help="Reviewer-only: write reviews/<review-id>.json")
    p_rv.add_argument("--target-commit", required=True, dest="target_commit")
    p_rv.add_argument("--report-file", required=True, dest="report_file")
    p_rv.add_argument("--agent-id", default=None, dest="agent_id")

    # wait-ci — block until the agent's own PR (or a specified PR) is CLEAN
    p_wci = sub.add_parser(
        "wait-ci",
        help="Block until a PR reaches CLEAN state via batched poll (no per-PR gh pr view).",
    )
    p_wci.add_argument("--pr", type=int, required=True, dest="pr_number", help="PR number to watch")
    p_wci.add_argument(
        "--repo", default="afokapu/atdd", help="GitHub repo (owner/repo)."
    )
    p_wci.add_argument(
        "--interval", type=int, default=180, metavar="SECONDS",
        help="Poll interval in seconds (default 180, min 60).",
    )

    # inbox — read/consume cli-return.jsonl entries (#824)
    p_inbox = sub.add_parser("inbox", help="Read cli-return.jsonl inbox (drain/peek)")
    p_inbox.add_argument(
        "inbox_action",
        choices=["drain", "peek"],
        help="drain: read + mark consumed. peek: read without consuming.",
    )
    p_inbox.add_argument("--agent-id", default=None, dest="agent_id")

    return parser


def run(argv: list[str]) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    sub = args.subcommand

    try:
        if sub == "heartbeat":
            path = cmd_heartbeat(
                agent_id=args.agent_id,
                current_step=args.current_step,
            )
            print(f"✓ heartbeat: {path}")
        elif sub == "event":
            data = json.loads(args.data) if args.data else None
            record = cmd_event(args.event_type, agent_id=args.agent_id, data=data)
            print(f"✓ event {record['event_type']} appended")
        elif sub == "commit":
            sha = cmd_commit(
                phase=args.phase,
                message=args.message,
                agent_id=args.agent_id,
                issue=args.issue,
                wmbt_urn=args.wmbt_urn,
                runtime_root=None,
            )
            print(f"✓ commit {sha[:12]} ({args.phase})")
        elif sub == "ask":
            record = cmd_ask(
                question=args.question,
                type=args.type,
                agent_id=args.agent_id,
            )
            print(f"✓ ask {record['question_id']} ({args.type})")
        elif sub == "escalate":
            cmd_escalate(
                reason=args.reason,
                severity=args.severity,
                agent_id=args.agent_id,
            )
            print(f"✓ escalate ({args.severity})")
        elif sub == "done":
            path = cmd_done(agent_id=args.agent_id, summary=args.summary)
            print(f"✓ done: {path}")
        elif sub == "context":
            ctx = cmd_context(agent_id=args.agent_id)
            print(json.dumps(ctx, indent=2, sort_keys=True))
        elif sub == "review":
            path = cmd_review(
                target_commit=args.target_commit,
                report_file=args.report_file,
                agent_id=args.agent_id,
            )
            print(f"✓ review: {path}")
        elif sub == "wait-ci":
            from atdd.coach.runtime.pr_watcher import PRWatcher
            interval = max(60, args.interval)
            watcher = PRWatcher(repo=args.repo, poll_interval=interval)
            result = watcher.wait_any(prs=[args.pr_number], target_state="CLEAN")
            print(f"CLEAN: #{result}")
        elif sub == "inbox":
            if args.inbox_action == "drain":
                entries = cmd_inbox_drain(agent_id=args.agent_id)
                for entry in entries:
                    print(json.dumps(entry))
            else:  # peek
                entries = cmd_inbox_peek(agent_id=args.agent_id)
                for entry in entries:
                    print(json.dumps(entry))
        else:
            parser.error(f"unknown subcommand: {sub}")
    except (  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        ValueError, FileNotFoundError,
    ) as exc:
        # User-facing CLI error: surface to stderr, return non-zero.
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    return 0


def run_cli(argv: list[str]) -> int:
    """Alias for run() — consistent naming with other coach commands."""
    return run(argv)


def main(argv: Optional[list[str]] = None) -> int:
    return run(list(sys.argv[1:] if argv is None else argv))
