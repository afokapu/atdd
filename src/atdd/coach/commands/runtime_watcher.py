"""Runtime watcher (#J5) — observes ``.atdd/runtime/agents/<id>/`` for
changes to the four well-known files (``heartbeat.json``,
``events.jsonl``, ``escalations.jsonl``, ``corrections.jsonl``) and
emits parsed events on the shared ``CoachEventQueue``.

Polling-based so the implementation is portable across Linux (inotify)
and macOS (fswatch); the latency budget is ≤1s per spec §4.4.

The reattachment contract (per ``event-semantics.md``) is implemented
via ``replay_from_disk()`` + ``mark_handled()`` + ``persist_checkpoint()``.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from atdd.coach.commands.event_queue import (
    CoachEventQueue,
    REPLAY_BEHAVIOR,
    natural_key,
)


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _jsonable(v: Any) -> Any:
    return v if v is None or isinstance(v, (str, int, float, bool)) else str(v)


class RuntimeWatcher:
    """Watches ``<runtime_dir>/agents/<id>/`` and emits to ``queue``."""

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
        self._thread = threading.Thread(
            target=self._loop, name="runtime-watcher", daemon=True
        )
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
            except Exception:  # never crash the daemon
                pass
            self._stop.wait(self.poll_interval)

    # --- one polling pass -------------------------------------------------

    def scan_once(self) -> int:
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
                if self._snapshots.get(path) == snap:
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
        except (OSError, json.JSONDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return 0
        event = {
            "event_type": "heartbeat",
            "agent_id": agent_id,
            "timestamp": _now_iso(),
            "payload": {
                "observed_at": data.get("observed_at") or _now_iso(),
                "pid": data.get("pid"),
                "status": data.get("status"),
                "source_file": "heartbeat.json",
            },
        }
        return 1 if self.queue.put(event) else 0

    def _emit_events_jsonl(self, agent_id: str, path: Path) -> int:
        emitted = 0
        for record in self._read_new_lines(path):
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
        except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
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
        if not self._agents_dir.is_dir():
            return 0
        emitted = 0
        for agent_dir in sorted(self._agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent_id = agent_dir.name
            events_path = agent_dir / "events.jsonl"
            if not events_path.exists():
                continue
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
                        if natural_key(record) in self._handled_keys:
                            continue
                        if self.queue.put(record):
                            emitted += 1
                stat = events_path.stat()
                self._jsonl_offsets[events_path] = stat.st_size
                self._snapshots[events_path] = _FileSnapshot(stat.st_mtime_ns, stat.st_size)
            except OSError:
                pass
        return emitted

    def mark_handled(self, event: dict) -> None:
        self._handled_keys.add(natural_key(event))

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
        except (OSError, json.JSONDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return
        for key in data.get("handled", []):
            self._handled_keys.add(tuple(key))
