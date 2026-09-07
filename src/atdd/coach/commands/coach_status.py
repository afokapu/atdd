"""`atdd coach status` — live inspection of an in-progress or recent coach run.

#616 (L001). Reads from:
  .atdd/runtime/coach/  (decisions, judgments)
  .atdd/runtime/agents/<id>/  (heartbeat, context)

Public surface:
  ``run_status(argv, *, runtime_dir)`` — entry point called by coach.run_cli.
  ``_build_status_parser()`` — argparse surface for `atdd coach status`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional


def _build_status_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atdd coach status",
        description=(
            "Inspect a live or recent atdd coach run. "
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
        "--decisions",
        type=int,
        default=10,
        metavar="N",
        help="Show last N decisions (default 10).",
    )
    p.add_argument(
        "--judgments",
        type=int,
        default=5,
        metavar="N",
        help="Show last N judgments (default 5).",
    )
    p.add_argument(
        "--watch",
        action="store_true",
        help="Refresh every 2s (clear + re-render loop, no curses).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="json_out",
        help="Machine-readable JSON output.",
    )
    return p


def run_status(
    argv: list[str],
    *,
    runtime_dir: Optional[Path] = None,
) -> int:
    """`atdd coach status` entry point.

    ``runtime_dir`` is injectable for tests; defaults to ``.atdd/runtime``
    relative to cwd, or the ``ATDD_RUNTIME_DIR`` env var if set.
    """
    import json
    import os
    import time

    from atdd.coach.runtime.reader import (
        derive_issue_phases,
        find_latest_run_id,
        list_run_ids,
        read_agent_sessions,
        read_decisions,
        read_judgments,
    )
    from atdd.coach.runtime.status_render import render_status_json, render_status_table

    parser = _build_status_parser()
    args = parser.parse_args(argv)

    if runtime_dir is None:
        env_dir = os.environ.get("ATDD_RUNTIME_DIR")
        runtime_dir = Path(env_dir) if env_dir else Path(".atdd") / "runtime"

    # Explicit --run-id that doesn't exist → exit non-0 with error on stderr
    if args.run_id is not None:
        known = list_run_ids(runtime_dir)
        if args.run_id not in known:
            print(
                f"Error: run '{args.run_id}' not found in {runtime_dir / 'coach'}",
                file=sys.stderr,
            )
            return 1

    def _render_once() -> tuple[int, str]:
        run_id = args.run_id if args.run_id is not None else find_latest_run_id(runtime_dir)
        sessions = read_agent_sessions(runtime_dir)

        if run_id is None:
            coach_path = runtime_dir / "coach"
            if args.json_out:
                return 0, json.dumps(
                    {"run_id": None, "issues": {}, "decisions": [], "judgments": [],
                     "sessions": sessions},
                    indent=2,
                )
            if sessions:
                lines = [f"No coach runs found in {coach_path}", "", "Agent sessions:"]
                for s in sessions:
                    lines.append(
                        f"  {s.get('agent_id', '?')}: Resume agent: claude --resume {s.get('claude_resume_uuid', '?')}"
                    )
                return 0, "\n".join(lines)
            return 0, f"No coach runs found in {coach_path}"

        decisions = read_decisions(run_id, args.decisions, runtime_dir=runtime_dir)
        judgments = read_judgments(args.judgments, runtime_dir=runtime_dir)
        issue_phases = derive_issue_phases(run_id, runtime_dir=runtime_dir)
        start_ts = decisions[0].timestamp if decisions else None

        if args.json_out:
            return 0, render_status_json(
                run_id, issue_phases, decisions, judgments,
                start_ts=start_ts, sessions=sessions,
            )
        return 0, render_status_table(
            run_id, issue_phases, decisions, judgments,
            start_ts=start_ts, sessions=sessions,
        )

    if args.watch:
        try:
            while True:
                rc, output = _render_once()
                print("\033[2J\033[H", end="")  # clear screen
                print(output)
                if rc != 0:
                    return rc
                time.sleep(2)
        except KeyboardInterrupt:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
            return 0

    rc, output = _render_once()
    print(output)
    return rc
