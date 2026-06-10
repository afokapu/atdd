"""``atdd coach dashboard`` — a reflowing worker-grid view of a coach run.

Sibling of ``atdd coach status`` (:mod:`atdd.coach.commands.coach_status`).
Both read the same runtime via :mod:`atdd.coach.runtime.reader`; ``status``
renders one table, ``dashboard`` renders one card per worker. The data gather
is shared so the two surfaces can never disagree.

Public surface:
  ``run_dashboard(argv, *, runtime_dir)`` — entry point called by ``coach.run_cli``.
  ``_build_dashboard_parser()`` — argparse surface.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional


def _build_dashboard_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atdd coach dashboard",
        description=(
            "Grid of per-worker cards for a live or recent atdd coach run. "
            "Reads from .atdd/runtime/coach/ and .atdd/runtime/agents/<id>/."
        ),
    )
    p.add_argument(
        "--run-id",
        default=None,
        dest="run_id",
        help="Inspect a specific run (default: most recent run).",
    )
    p.add_argument(
        "--watch",
        action="store_true",
        help="Refresh every 2s (clear + re-render loop, no curses).",
    )
    p.add_argument(
        "--width",
        type=int,
        default=None,
        help="Override terminal width (default: detected, fallback 80).",
    )
    p.add_argument(
        "--all",
        action="store_true",
        dest="scope_all",
        help="Show every worker on disk, not just the current run's (historical view).",
    )
    return p


def _term_width(override: Optional[int]) -> int:
    if override:
        return override
    try:
        return shutil.get_terminal_size((80, 24)).columns
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return 80


def _last_event_time(events_path: Path) -> Optional["datetime"]:
    """Timestamp of the last line in an agent ``events.jsonl`` (last activity)."""
    import json
    from datetime import datetime, timezone

    if not events_path.exists():
        return None
    last = ""
    try:
        with events_path.open("r", encoding="utf-8") as fh:
            for line in fh:  # cheap enough; tail-seek is a later optimization
                if line.strip():
                    last = line
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None
    if not last:
        return None
    try:
        rec = json.loads(last)
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None
    raw = rec.get("occurred_at") or rec.get("timestamp")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None


def _parse_iso(raw) -> Optional["datetime"]:
    from datetime import datetime, timezone

    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None


def _run_issues(runtime_dir: Path, run_id: str) -> set:
    """Issue numbers driven by ``run_id`` (authoritative: runs/<id>/status.json).

    Falls back to parsing the lead issue out of the ``run-<issue>-...`` id when
    no status record is present.
    """
    import json

    status = runtime_dir / "runs" / run_id / "status.json"
    if status.exists():
        try:
            s = json.loads(status.read_text(encoding="utf-8"))
            if s.get("issue_number") is not None:
                return {int(s["issue_number"])}
        except (json.JSONDecodeError, OSError, ValueError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            pass
    parts = run_id.split("-")
    if len(parts) >= 2 and parts[1].isdigit():
        return {int(parts[1])}
    return set()


def _read_workers(runtime_dir: Path, run_id: str, *, scope_all: bool) -> list:
    """Gather workers for the current run from coach session rosters.

    Default scope is the issue(s) the run drives (``runs/<id>/status.json``);
    each worker is a ``coach/<issue>/*.session.json`` record (issue, persona,
    phase, spawned_at). ``scope_all`` widens to every session on disk — the
    historical view. Last-activity for stall detection comes from the worker's
    ``agents/<id>/events.jsonl`` tail.
    """
    import json

    from atdd.coach.runtime.dashboard import Worker

    coach_dir = runtime_dir / "coach"
    if not coach_dir.exists():
        return []

    if scope_all:
        issue_dirs = [d for d in sorted(coach_dir.iterdir()) if d.is_dir()]
    else:
        issues = _run_issues(runtime_dir, run_id)
        issue_dirs = [coach_dir / str(i) for i in sorted(issues) if (coach_dir / str(i)).is_dir()]

    workers: list[Worker] = []
    for issue_dir in issue_dirs:
        for sf in sorted(issue_dir.glob("*.session.json")):
            try:
                s = json.loads(sf.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
                continue
            agent_id = s.get("agent_id", sf.stem.replace(".session", ""))
            phase = s.get("phase")
            workers.append(
                Worker(
                    issue=s.get("issue"),
                    role=s.get("persona") or "?",
                    started_at=_parse_iso(s.get("spawned_at")),
                    last_heartbeat=_last_event_time(runtime_dir / "agents" / agent_id / "events.jsonl"),
                    phase=phase.upper() if isinstance(phase, str) else None,
                    agent_id=agent_id,
                )
            )
    return workers


def run_dashboard(argv: list[str], *, runtime_dir: Optional[Path] = None) -> int:
    """``atdd coach dashboard`` entry point.

    ``runtime_dir`` is injectable for tests; defaults to ``.atdd/runtime``
    relative to cwd, or the ``ATDD_RUNTIME_DIR`` env var if set.
    """
    from atdd.coach.runtime.dashboard import build_cards, render_grid
    from atdd.coach.runtime.reader import (
        derive_issue_phases,
        find_latest_run_id,
        list_run_ids,
        read_decisions,
    )

    args = _build_dashboard_parser().parse_args(argv)

    if runtime_dir is None:
        env_dir = os.environ.get("ATDD_RUNTIME_DIR")
        runtime_dir = Path(env_dir) if env_dir else Path(".atdd") / "runtime"

    if args.run_id is not None:
        known = (runtime_dir / "runs" / args.run_id).exists() or args.run_id in list_run_ids(
            runtime_dir
        )
        if not known:
            print(
                f"Error: run '{args.run_id}' not found in {runtime_dir / 'runs'}",
                file=sys.stderr,
            )
            return 1

    def _render_once() -> str:
        run_id = args.run_id if args.run_id is not None else find_latest_run_id(runtime_dir)
        if run_id is None:
            return f"No coach runs found in {runtime_dir / 'coach'}"

        issue_phases = derive_issue_phases(run_id, runtime_dir=runtime_dir)
        workers = _read_workers(runtime_dir, run_id, scope_all=args.scope_all)
        decisions = read_decisions(run_id, 50, runtime_dir=runtime_dir)

        cards = build_cards(
            agent_states=workers,
            issue_phases=issue_phases,
            decisions=decisions,
        )
        header = f"atdd coach dashboard · run {run_id} · {len(cards)} worker(s)"
        return header + "\n\n" + render_grid(cards, _term_width(args.width))

    if args.watch:
        try:
            while True:
                print("\033[2J\033[H", end="")
                print(_render_once())
                time.sleep(2)
        except KeyboardInterrupt:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return 0

    print(_render_once())
    return 0
