"""CLI controller for the coach runtime — `atdd coach <start|wait|next|stop|daemons>`.

Thin shell: parse the verb + flags, build the use case from the repo via the
composition root, and run it. All wiring lives in composition.py; the
wait/cursor decision lives in the pure domain core. ``next`` is an alias for
``wait`` so a chat-session coach can loop the completing command under either
name.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

VERBS = ("start", "wait", "next", "stop", "daemons")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach",
        description=(
            "Coach-session runtime: start the workspace-scoped feed_daemon and "
            "surface its escalations back to the session (closes the autonomous loop)."
        ),
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    p_start = sub.add_parser("start", help="run the gate and launch the scoped daemon")
    p_start.add_argument("--workspace", required=True, help="cmux workspace id")
    p_start.add_argument(
        "--no-gate", action="store_true", help="skip the atdd gate preflight"
    )
    p_start.add_argument(
        "--interval", type=float, default=2.0, help="daemon poll interval seconds"
    )

    for name, help_text in (
        ("wait", "block until the next escalation, print it as one JSON line, exit"),
        ("next", "alias for wait"),
    ):
        p_wait = sub.add_parser(name, help=help_text)
        p_wait.add_argument("--workspace", required=True, help="cmux workspace id")
        p_wait.add_argument(
            "--poll-interval", type=float, default=1.0, dest="poll_interval"
        )
        p_wait.add_argument(
            "--follow",
            action="store_true",
            help="stream every new escalation instead of exiting after one",
        )

    p_stop = sub.add_parser("stop", help="stop managed daemon(s) by pidfile")
    p_stop.add_argument(
        "--workspace", default=None, help="workspace to stop (default: all managed)"
    )

    p_daemons = sub.add_parser("daemons", help="list managed daemons and their status")
    p_daemons.add_argument(
        "--json", action="store_true", dest="json_out", help="machine-readable output"
    )

    return parser


def run(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    from atdd.mediate_worker_decisions.coach_runtime.composition import (
        build_coach_runtime_from_repo,
        resolve_workspace_paths,
    )

    runtime = build_coach_runtime_from_repo()

    if args.verb == "start":
        paths = resolve_workspace_paths(args.workspace)
        daemon = runtime.start(
            args.workspace,
            lock_path=paths["lock_path"],
            escalations_path=paths["escalations_path"],
            verdicts_path=paths["verdicts_path"],
            run_gate=not args.no_gate,
        )
        print(
            f"coach: daemon for workspace {args.workspace!r} running (pid {daemon.pid})"
        )
        return 0

    if args.verb in ("wait", "next"):
        from atdd.mediate_worker_decisions.coach_runtime.src.integration.jsonl_escalation_reader import (
            FileCursorStore,
            JsonlEscalationReader,
        )
        from atdd.mediate_worker_decisions.feed_daemon.src.integration.signal_stop import (
            RealSleeper,
            SignalStop,
        )

        paths = resolve_workspace_paths(args.workspace)
        reader = JsonlEscalationReader(Path(paths["escalations_path"]))
        cursor = FileCursorStore(Path(paths["cursor_path"]))
        sleeper = RealSleeper()
        stop = SignalStop().install()  # SIGINT/SIGTERM ends the blocking wait

        while True:
            record = runtime.wait_next(
                reader=reader,
                cursor_store=cursor,
                sleeper=sleeper,
                stop=stop,
                poll_interval=args.poll_interval,
            )
            if record is None:
                return 0
            sys.stdout.write(json.dumps(record) + "\n")
            sys.stdout.flush()
            if not args.follow:
                return 0  # exit-after-one is the loop contract

    if args.verb == "stop":
        stopped = runtime.stop(args.workspace)
        if not stopped:
            print("coach: no managed daemons to stop")
        for daemon in stopped:
            print(f"coach: stopped daemon for workspace {daemon.workspace_id!r}")
        return 0

    if args.verb == "daemons":
        listing = runtime.list_daemons()
        if args.json_out:
            print(
                json.dumps(
                    [
                        {**d.to_record(), "status": d.status}
                        for d in listing
                    ]
                )
            )
            return 0
        if not listing:
            print("coach: no managed daemons")
            return 0
        for d in listing:
            print(f"  {d.workspace_id}\tpid {d.pid}\t{d.status}")
        return 0

    return 2  # unreachable: argparse rejects unknown verbs


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
