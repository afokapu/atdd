"""Git watcher — observes HEAD advancement on coach-watched worktrees.

Spec references:
- §3.2 (runtime folder layout — `agents/<id>/events.jsonl`,
        `validations/<sha>/violations.jsonl`)
- §6.4 step 1 (commit observation) and step 2 (trailer parsing →
        validation_pending event keying)
- §7.3 (commit trailers — mechanically enforced)
- §C0 (`runtime-event.schema.json`, `validator-result.schema.json`)

Public surface:
- ``GitWatcher`` — per-agent watcher that, given a SHA, emits
  ``commit_observed`` and ``validation_pending`` events to the agent's
  ``events.jsonl`` and writes ``coach.commit-trailers.*`` violations to
  the per-SHA ``validations/<sha>/violations.jsonl`` when required
  trailers are absent or malformed.
- ``parse_trailers`` — best-effort RFC-822-style trailer parser that
  delegates to ``git interpret-trailers --parse`` when available.

Design notes:
- Append-only writes use ``os.open(... O_APPEND | O_CREAT | O_WRONLY)``
  with a single ``os.write`` per record, mirroring ``DecisionWriter``.
- The watcher does no polling itself — callers (the broader runtime
  watcher in #510) drive ``observe(sha=...)`` once per HEAD advance.
- The trailer-parser violations are written directly by the watcher's
  emit path. The pytest violation-collector plugin (#M2) will replace
  this writer once it ships; the rule-IDs are stable.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


REQUIRED_TRAILERS: tuple[str, ...] = ("Phase", "WMBT-Urn", "Agent-Id", "Issue")

_TRAILER_RULE_IDS: dict[str, str] = {
    "Phase": "coach.commit-trailers.phase-required",
    "WMBT-Urn": "coach.commit-trailers.wmbt-urn-required",
    "Agent-Id": "coach.commit-trailers.agent-id-required",
    "Issue": "coach.commit-trailers.issue-required",
}


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _append_jsonl(path: Path, record: dict) -> None:
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    data = line.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def _git(args: Iterable[str], *, cwd: Path) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=str(cwd), text=True
    ).rstrip("\n")


def parse_trailers(message: str, *, cwd: Optional[Path] = None) -> dict[str, str]:
    """Parse RFC-822-style trailers from a commit message.

    Prefers ``git interpret-trailers --parse`` when ``cwd`` is given so
    parsing matches git's own producer-side validation. Falls back to a
    line-based parser keyed on ``<Token>: <value>`` over the trailing
    block of the message.
    """
    if cwd is not None:
        try:
            out = subprocess.check_output(
                ["git", "interpret-trailers", "--parse"],
                input=message,
                text=True,
                cwd=str(cwd),
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            out = ""
        if out.strip():
            trailers: dict[str, str] = {}
            for line in out.splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    trailers[key.strip()] = value.strip()
            return trailers

    trailers: dict[str, str] = {}
    for line in reversed(message.strip().splitlines()):
        line = line.rstrip()
        if not line:
            if trailers:
                break
            continue
        if ":" not in line:
            break
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key or " " in key:
            break
        trailers[key] = value
    return trailers


@dataclass(frozen=True)
class _CommitFacts:
    sha: str
    parent_sha: str
    message: str
    trailers: dict[str, str]


class GitWatcher:
    """Per-agent watcher that emits commit_observed + validation_pending.

    Args:
        agent_id: Coach-issued agent identifier (matches the directory
            name under ``.atdd/runtime/agents/``).
        worktree: Path to the agent's git worktree on disk.
        runtime_dir: Path to the coach runtime root (typically
            ``.atdd/runtime``).
    """

    def __init__(
        self,
        *,
        agent_id: str,
        worktree: Path,
        runtime_dir: Path,
    ) -> None:
        self.agent_id = agent_id
        self.worktree = Path(worktree)
        self.runtime_dir = Path(runtime_dir)

    @property
    def events_path(self) -> Path:
        return self.runtime_dir / "agents" / self.agent_id / "events.jsonl"

    def observe(self, *, sha: Optional[str] = None) -> None:
        """Observe one commit, parse trailers, emit downstream events."""
        if sha is None:
            sha = _git(["rev-parse", "HEAD"], cwd=self.worktree)
        facts = self._collect_commit_facts(sha)

        self._emit_commit_observed(facts)
        self._emit_trailer_violations(facts)
        self._emit_validation_pending(facts)

    def _collect_commit_facts(self, sha: str) -> _CommitFacts:
        message = _git(["log", "-1", "--format=%B", sha], cwd=self.worktree)
        parent_raw = _git(["log", "-1", "--format=%P", sha], cwd=self.worktree)
        parent_sha = parent_raw.split()[0] if parent_raw.strip() else ""
        trailers = parse_trailers(message, cwd=self.worktree)
        return _CommitFacts(
            sha=sha,
            parent_sha=parent_sha,
            message=message,
            trailers=trailers,
        )

    def _emit_commit_observed(self, facts: _CommitFacts) -> None:
        event = {
            "event_type": "commit_observed",
            "agent_id": self.agent_id,
            "timestamp": _utc_now_iso(),
            "payload": {
                "worktree": str(self.worktree),
                "sha": facts.sha,
                "parent_sha": facts.parent_sha,
                "trailers": dict(facts.trailers),
            },
        }
        _append_jsonl(self.events_path, event)

    def _emit_validation_pending(self, facts: _CommitFacts) -> None:
        phase = facts.trailers.get("Phase", "")
        scope = {
            "wmbt_urn": facts.trailers.get("WMBT-Urn", ""),
            "agent_id": facts.trailers.get("Agent-Id", self.agent_id),
            "issue": facts.trailers.get("Issue", ""),
        }
        event = {
            "event_type": "validation_pending",
            "agent_id": self.agent_id,
            "timestamp": _utc_now_iso(),
            "payload": {
                "sha": facts.sha,
                "worktree": str(self.worktree),
                "phase": phase,
                "scope": scope,
            },
        }
        _append_jsonl(self.events_path, event)

    def _emit_trailer_violations(self, facts: _CommitFacts) -> None:
        violations_path = (
            self.runtime_dir / "validations" / facts.sha / "violations.jsonl"
        )
        for trailer in REQUIRED_TRAILERS:
            value = facts.trailers.get(trailer, "")
            if value:
                continue
            rule_id = _TRAILER_RULE_IDS[trailer]
            record = {
                "validator_id": "coach.runtime.git_watcher::observe",
                "rule_id": rule_id,
                "severity": 4,
                "disposition": "strict",
                "location": f"{facts.sha}:0",
                "detail": (
                    f"commit message is missing required trailer {trailer!r}; "
                    "see src/atdd/coach/conventions/commit-trailers.convention.yaml"
                ),
                "suppression_marker": None,
            }
            _append_jsonl(violations_path, record)


__all__ = ["GitWatcher", "parse_trailers", "REQUIRED_TRAILERS"]
