"""Liveness checker (#J5) — periodic timer that emits
``process_silence`` when an agent's heartbeat is older than
``silence_seconds``.

Per spec §4.4 the default tick is 30s and the default silence threshold
comes from ``coach.process_silence_seconds``. Bounded emissions: each
silence window produces exactly one ``process_silence`` event;
heartbeat resumption resets the window.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from atdd.coach.commands.event_queue import CoachEventQueue


class LivenessChecker:
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
        self._silence_window: dict[str, str] = {}
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
        except (OSError, json.JSONDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return (None, float("inf"))
        observed = data.get("observed_at")
        if not observed:
            return (None, float("inf"))
        try:
            ts = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return (observed, float("inf"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        elapsed = (now - ts).total_seconds()
        return (observed, elapsed)
