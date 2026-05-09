"""Coach v9 runtime/git/liveness watchers (#J5).

Three concurrent event sources per spec §4.4 feed a **single** coach
event queue with the idempotency, ordering, and replay contracts from
``event-semantics.md`` (#483):

- ``RuntimeWatcher`` — file-system watcher on
  ``.atdd/runtime/agents/*/`` (heartbeat.json, events.jsonl,
  escalations.jsonl, corrections.jsonl). On change, parses the file and
  pushes events onto the shared queue. Polling-based; the latency
  contract is ≤1s.
- ``GitWatcher`` — observes new commits on each worktree's HEAD via
  ``git rev-parse``, plus PR-state via an injectable ``gh pr view``
  callback. Emits ``commit_observed`` (with parsed commit trailers per
  spec §6.4 step 1), ``pr_opened``, ``pr_closed``.
- ``LivenessChecker`` — periodic timer (default 30s) that reads each
  agent's ``heartbeat.json``; emits ``process_silence`` when elapsed
  exceeds ``silence_seconds``. Bounded emissions: one per silence
  window, not one per timer tick.

The shared queue ``CoachEventQueue`` enforces per-event-type natural-key
deduplication (per ``event-semantics.md``) so consumers see each event
exactly once even when at-least-once producers re-fire.

Reattachment contract: after a watcher restart, ``replay_from_disk()``
re-reads the agents' ``events.jsonl`` and republishes events. The
checkpoint persisted via ``persist_checkpoint()`` records which events
have been *handled* by a downstream consumer; replay-cached events
whose handlers completed are not re-emitted; replay-suppressed events
(per ``event-semantics.md``) are never re-emitted; at-least-once events
are deduped by the queue's natural-key layer.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


# ---------------------------------------------------------------------------
# Event-semantics tables — frozen at C0; mirrors event-semantics.md
# ---------------------------------------------------------------------------

# How a queue/replay layer dedupes an at-least-once event into a single
# "consumer-visible" emission. Each entry is the tuple of payload-path
# components (plus optional top-level keys like ``agent_id``) that form
# the natural key. Per event-semantics.md:
NATURAL_KEY: dict[str, tuple[str, ...]] = {
    "agent_spawned":       ("agent_id",),
    "heartbeat":           ("agent_id", "payload.observed_at"),
    "commit_observed":     ("payload.sha",),
    "event_emitted":       ("payload.original_event_id", "payload.original_event_type"),
    "escalation_emitted":  ("payload.judgment_id",),
    "pr_opened":           ("payload.pr_number",),
    "pr_closed":           ("payload.pr_number", "payload.terminal_state"),
    "validation_pending":  ("payload.coach_run_id", "payload.phase", "payload.sha"),
    "validation_complete": ("payload.coach_run_id", "payload.phase", "payload.sha"),
    "review_complete":     ("payload.issue_number", "payload.aggregate_sha"),
    "correction_emitted":  ("agent_id", "payload.rule_id", "payload.detected_at"),
    "process_silence":     ("agent_id", "payload.silence_window_started_at"),
}

# Replay behavior on coach --resume / watcher restart.
#   "cached"     — republish the prior event from durable state
#   "suppressed" — never re-emit on resume
REPLAY_BEHAVIOR: dict[str, str] = {
    "agent_spawned":       "cached",
    "heartbeat":           "suppressed",
    "commit_observed":     "cached",
    "event_emitted":       "cached",
    "escalation_emitted":  "suppressed",
    "pr_opened":           "cached",
    "pr_closed":           "cached",
    "validation_pending":  "suppressed",
    "validation_complete": "cached",
    "review_complete":     "cached",
    "correction_emitted":  "suppressed",
    "process_silence":     "suppressed",
}


def _natural_key(event: dict) -> tuple:
    """Return the dedup key for an event per ``NATURAL_KEY``.

    For unknown event types, fall back to the full event-type +
    timestamp identity so unrelated events never collide.
    """
    et = event.get("event_type")
    paths = NATURAL_KEY.get(et)
    if paths is None:
        return (et, event.get("timestamp"), id(event))
    parts: list[Any] = [et]
    for path in paths:
        if "." in path:
            top, rest = path.split(".", 1)
            parts.append((event.get(top) or {}).get(rest))
        else:
            parts.append(event.get(path))
    return tuple(parts)


# ---------------------------------------------------------------------------
# Single shared event queue
# ---------------------------------------------------------------------------


class CoachEventQueue:
    """Single coach event queue shared by all three watchers.

    Enforces per-event-type natural-key dedup so at-least-once producers
    surface as exactly-once to the consumer.
    """

    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = Path(runtime_dir)
        self._items: deque[dict] = deque()
        self._seen: set[tuple] = set()
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)

    def put(self, event: dict) -> bool:
        """Enqueue ``event`` if its natural key has not been seen.

        Returns ``True`` if accepted, ``False`` if deduped.
        """
        key = _natural_key(event)
        with self._cv:
            if key in self._seen:
                return False
            self._seen.add(key)
            self._items.append(event)
            self._cv.notify()
            return True

    def get(self, timeout: Optional[float] = None) -> Optional[dict]:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cv:
            while not self._items:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return None
                self._cv.wait(timeout=remaining)
            return self._items.popleft()

    def drain(self) -> list[dict]:
        with self._cv:
            out = list(self._items)
            self._items.clear()
            return out

    def __len__(self) -> int:
        with self._cv:
            return len(self._items)


# ---------------------------------------------------------------------------
# Runtime watcher (.atdd/runtime/agents/<id>/*)
# ---------------------------------------------------------------------------

_RUNTIME_FILES: tuple[str, ...] = (
    "heartbeat.json",
    "events.jsonl",
    "escalations.jsonl",
    "corrections.jsonl",
)


@dataclass
class _FileSnapshot:
    mtime_ns: int
    size: int


class RuntimeWatcher:
    """Watches ``<runtime_dir>/agents/<id>/`` for changes to the four
    well-known files; emits parsed events on the shared queue.
    """

    def __init__(
        self,
        runtime_dir: Path,
        queue: CoachEventQueue,
        *,
        poll_interval: float = 0.2,
    ) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.queue = queue
        self.poll_interval = poll_interval
        self._agents_dir = self.runtime_dir / "agents"
        self._snapshots: dict[Path, _FileSnapshot] = {}
        self._jsonl_offsets: dict[Path, int] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._handled_keys: set[tuple] = set()
        self._checkpoint_path = self.runtime_dir / "coach" / "watcher-checkpoint.json"
        self._load_checkpoint()

    # --- background loop --------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="runtime-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception:  # pragma: no cover — defensive; never crash the daemon
                pass
            self._stop.wait(self.poll_interval)

    # --- one polling pass -------------------------------------------------

    def scan_once(self) -> int:
        """One polling pass over the agent tree. Returns events emitted."""
        if not self._agents_dir.is_dir():
            return 0
        emitted = 0
        for agent_dir in sorted(self._agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            for fname in _RUNTIME_FILES:
                path = agent_dir / fname
                if not path.exists():
                    continue
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                snap = _FileSnapshot(stat.st_mtime_ns, stat.st_size)
                prev = self._snapshots.get(path)
                if prev == snap:
                    continue
                self._snapshots[path] = snap
                emitted += self._emit_for_file(agent_id, path)
        return emitted

    # --- per-file event derivation ---------------------------------------

    def _emit_for_file(self, agent_id: str, path: Path) -> int:
        if path.name == "heartbeat.json":
            return self._emit_heartbeat(agent_id, path)
        if path.name == "events.jsonl":
            return self._emit_events_jsonl(agent_id, path)
        if path.name == "corrections.jsonl":
            return self._emit_corrections_jsonl(agent_id, path)
        if path.name == "escalations.jsonl":
            return self._emit_escalations_jsonl(agent_id, path)
        return 0

    def _emit_heartbeat(self, agent_id: str, path: Path) -> int:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        observed_at = data.get("observed_at") or _now_iso()
        event = {
            "event_type": "heartbeat",
            "agent_id": agent_id,
            "timestamp": _now_iso(),
            "payload": {
                "observed_at": observed_at,
                "pid": data.get("pid"),
                "status": data.get("status"),
                "source_file": "heartbeat.json",
            },
        }
        return 1 if self.queue.put(event) else 0

    def _emit_events_jsonl(self, agent_id: str, path: Path) -> int:
        new_records = self._read_new_lines(path)
        emitted = 0
        for record in new_records:
            ev = dict(record)
            ev.setdefault("agent_id", agent_id)
            ev.setdefault("timestamp", _now_iso())
            payload = dict(ev.get("payload") or {})
            payload.setdefault("source_file", "events.jsonl")
            ev["payload"] = payload
            if self.queue.put(ev):
                emitted += 1
        return emitted

    def _emit_corrections_jsonl(self, agent_id: str, path: Path) -> int:
        emitted = 0
        for record in self._read_new_lines(path):
            event = {
                "event_type": "correction_emitted",
                "agent_id": record.get("agent_id", agent_id),
                "timestamp": _now_iso(),
                "payload": {
                    "rule_id": record.get("rule_id"),
                    "detected_at": record.get("detected_at"),
                    "injection_method": record.get("injection_method"),
                    "source_file": "corrections.jsonl",
                },
            }
            if self.queue.put(event):
                emitted += 1
        return emitted

    def _emit_escalations_jsonl(self, agent_id: str, path: Path) -> int:
        emitted = 0
        for record in self._read_new_lines(path):
            event = {
                "event_type": "escalation_emitted",
                "agent_id": record.get("agent_id", agent_id),
                "timestamp": _now_iso(),
                "payload": {
                    "judgment_id": record.get("judgment_id"),
                    "target": record.get("target"),
                    "source_file": "escalations.jsonl",
                },
            }
            if self.queue.put(event):
                emitted += 1
        return emitted

    def _read_new_lines(self, path: Path) -> list[dict]:
        try:
            with path.open("r", encoding="utf-8") as fh:
                fh.seek(self._jsonl_offsets.get(path, 0))
                blob = fh.read()
                self._jsonl_offsets[path] = fh.tell()
        except OSError:
            return []
        records: list[dict] = []
        for line in blob.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records

    # --- reattachment / checkpointing -----------------------------------

    def replay_from_disk(self) -> int:
        """Reconstruct event delivery from disk-persisted state.

        For each event in each agent's ``events.jsonl``:
          - if its ``REPLAY_BEHAVIOR`` is ``suppressed``, skip;
          - if its ``natural key`` is in the persisted checkpoint
            (handler already completed), skip;
          - otherwise, republish onto the queue.

        Also primes ``_jsonl_offsets`` so the live polling path picks
        up *only* new lines after replay.
        """
        if not self._agents_dir.is_dir():
            return 0
        emitted = 0
        for agent_dir in sorted(self._agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            events_path = agent_dir / "events.jsonl"
            if events_path.exists():
                try:
                    with events_path.open("r", encoding="utf-8") as fh:
                        for line in fh:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                record = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            record.setdefault("agent_id", agent_id)
                            record.setdefault("payload", {})
                            et = record.get("event_type")
                            if REPLAY_BEHAVIOR.get(et) == "suppressed":
                                continue
                            if _natural_key(record) in self._handled_keys:
                                continue
                            if self.queue.put(record):
                                emitted += 1
                    self._jsonl_offsets[events_path] = events_path.stat().st_size
                    self._snapshots[events_path] = _FileSnapshot(
                        events_path.stat().st_mtime_ns, events_path.stat().st_size
                    )
                except OSError:
                    pass
        return emitted

    def mark_handled(self, event: dict) -> None:
        self._handled_keys.add(_natural_key(event))

    def persist_checkpoint(self) -> None:
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        keys = [list(map(_jsonable, k)) for k in self._handled_keys]
        tmp = self._checkpoint_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"handled": keys}), encoding="utf-8")
        os.replace(tmp, self._checkpoint_path)

    def _load_checkpoint(self) -> None:
        if not self._checkpoint_path.exists():
            return
        try:
            data = json.loads(self._checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for key in data.get("handled", []):
            self._handled_keys.add(tuple(key))


def _jsonable(v: Any) -> Any:
    return v if v is None or isinstance(v, (str, int, float, bool)) else str(v)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ---------------------------------------------------------------------------
# Git watcher
# ---------------------------------------------------------------------------


_TRAILER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):\s*(.+)\s*$")


def parse_commit_trailers(message: str) -> dict[str, str]:
    """Parse RFC-2822-style trailers from a git commit message.

    Trailers are the last contiguous block of ``Key: value`` lines at
    the end of the message. Recognized keys per spec §6.4 step 1
    (``Agent-Id``, ``Issue``, ``WMBT-Urn``, ``Phase``) are returned
    along with any other trailer keys present.
    """
    lines = message.rstrip("\n").splitlines()
    trailers: dict[str, str] = {}
    for line in reversed(lines):
        if not line.strip():
            if trailers:
                break
            continue
        m = _TRAILER_RE.match(line)
        if not m:
            break
        trailers[m.group(1)] = m.group(2).strip()
    return trailers


class GitWatcher:
    """Observes new commits on worktree HEADs and PR-state transitions.

    ``gh_pr_view`` is an injected callable returning the PR-state dict
    for a worktree (or ``None`` if no PR). The default value is ``None``
    which disables PR observation; tests inject a fake.
    """

    def __init__(
        self,
        worktree_paths: Iterable[Path],
        queue: CoachEventQueue,
        *,
        gh_pr_view: Optional[Callable[[Path], Optional[dict]]] = None,
    ) -> None:
        self.worktree_paths = [Path(p) for p in worktree_paths]
        self.queue = queue
        self._gh_pr_view = gh_pr_view
        self._last_sha: dict[Path, str] = {}
        self._last_pr_state: dict[Path, str] = {}

    def scan_once(self) -> int:
        emitted = 0
        for wt in self.worktree_paths:
            emitted += self._scan_commits(wt)
            emitted += self._scan_pr_state(wt)
        return emitted

    def _scan_commits(self, wt: Path) -> int:
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 0
        prev = self._last_sha.get(wt)
        self._last_sha[wt] = sha
        if prev is None or sha == prev:
            return 0
        try:
            branch = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout.strip()
            message = subprocess.run(
                ["git", "log", "-1", "--format=%B", sha],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout
            parent = subprocess.run(
                ["git", "log", "-1", "--format=%P", sha],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout.strip().split()
            author = subprocess.run(
                ["git", "log", "-1", "--format=%an <%ae>", sha],
                cwd=wt, capture_output=True, text=True, check=True,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return 0
        event = {
            "event_type": "commit_observed",
            "agent_id": None,
            "timestamp": _now_iso(),
            "payload": {
                "sha": sha,
                "parent_sha": parent[0] if parent else None,
                "branch": branch,
                "worktree_path": str(wt),
                "author": author,
                "trailers": parse_commit_trailers(message),
            },
        }
        return 1 if self.queue.put(event) else 0

    def _scan_pr_state(self, wt: Path) -> int:
        if self._gh_pr_view is None:
            return 0
        try:
            state = self._gh_pr_view(wt)
        except Exception:  # pragma: no cover
            return 0
        if state is None:
            return 0
        terminal = state.get("state")
        prev = self._last_pr_state.get(wt)
        self._last_pr_state[wt] = terminal
        if prev is None and terminal == "OPEN":
            event = {
                "event_type": "pr_opened",
                "agent_id": None,
                "timestamp": _now_iso(),
                "payload": {
                    "pr_number": state.get("number"),
                    "sha": state.get("headRefOid"),
                    "base": state.get("baseRefName"),
                    "head": state.get("headRefName"),
                },
            }
            return 1 if self.queue.put(event) else 0
        if prev == "OPEN" and terminal != "OPEN":
            event = {
                "event_type": "pr_closed",
                "agent_id": None,
                "timestamp": _now_iso(),
                "payload": {
                    "pr_number": state.get("number"),
                    "sha": state.get("headRefOid"),
                    "terminal_state": terminal,
                },
            }
            return 1 if self.queue.put(event) else 0
        return 0


# ---------------------------------------------------------------------------
# Liveness checker
# ---------------------------------------------------------------------------


class LivenessChecker:
    """30s-tick checker that emits ``process_silence`` when an agent's
    heartbeat is older than ``silence_seconds``.

    Bounded emissions: each silence window produces exactly one event.
    A heartbeat resumption resets the window; if silence resumes, a new
    window begins.
    """

    def __init__(
        self,
        runtime_dir: Path,
        queue: CoachEventQueue,
        *,
        silence_seconds: int = 30,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.queue = queue
        self.silence_seconds = silence_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._silence_window: dict[str, str] = {}  # agent_id -> window_start_iso
        self._agents_dir = self.runtime_dir / "agents"

    def tick(self) -> int:
        if not self._agents_dir.is_dir():
            return 0
        now = self._clock()
        emitted = 0
        for agent_dir in sorted(self._agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            last_hb_iso, elapsed = self._read_heartbeat_age(agent_dir, now)
            if elapsed is None or elapsed < self.silence_seconds:
                # heartbeat fresh (or freshly resumed) → close any open window
                self._silence_window.pop(agent_id, None)
                continue
            window_start = self._silence_window.get(agent_id)
            if window_start is None:
                window_start = last_hb_iso or now.isoformat()
                self._silence_window[agent_id] = window_start
                elapsed_int = int(elapsed) if elapsed != float("inf") else None
                event = {
                    "event_type": "process_silence",
                    "agent_id": agent_id,
                    "timestamp": now.isoformat(),
                    "payload": {
                        "last_heartbeat_at": last_hb_iso,
                        "elapsed_seconds": elapsed_int,
                        "silence_window_started_at": window_start,
                    },
                }
                if self.queue.put(event):
                    emitted += 1
        return emitted

    def _read_heartbeat_age(
        self, agent_dir: Path, now: datetime
    ) -> tuple[Optional[str], Optional[float]]:
        hb = agent_dir / "heartbeat.json"
        if not hb.exists():
            return (None, float("inf"))
        try:
            data = json.loads(hb.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return (None, float("inf"))
        observed = data.get("observed_at")
        if not observed:
            return (None, float("inf"))
        try:
            ts = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        except ValueError:
            return (observed, float("inf"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        elapsed = (now - ts).total_seconds()
        return (observed, elapsed)
