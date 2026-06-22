"""`atdd state` command surface (#1168 Phase 1, #1177).

Phase 1 ships two enforcement commands described in #1168:

- ``atdd state doctor`` — print the detected layout (Control Root, Git worktree
  root, layout mode, State Store path) and a status line.
- ``atdd state layout --check`` — validate the filesystem layout is legal and
  exit non-zero on a violation (e.g. a per-worktree State Store).

``atdd state init`` / ``migrate-layout`` / the SQLite migrations are #1168
Phases 2+ and are intentionally not implemented here.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Optional, Sequence, Tuple

from atdd.state.paths import (
    AmbiguousControlRootError,
    ControlRootNotFoundError,
    ControlRootResolution,
    check_layout,
    resolve_control_root,
)

_log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd state",
        description="ATDD State Store — local operational data (#1168).",
    )
    sub = parser.add_subparsers(dest="op")

    doctor = sub.add_parser("doctor", help="Print and validate the detected State Store layout.")
    doctor.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    layout = sub.add_parser("layout", help="Layout guards.")
    layout.add_argument("--check", action="store_true", help="Validate the layout; non-zero on violation.")
    layout.add_argument("--root", default=None, help="Starting directory (default: cwd).")

    return parser


def _start_dir(root: Optional[str]) -> Path:
    return Path(root).resolve() if root else Path.cwd()


def _resolve_or_report(start: Path) -> Tuple[Optional[ControlRootResolution], int]:
    """Resolve the Control Root, or log + print the error and return an exit code.

    Returns ``(resolution, 0)`` on success or ``(None, 2)`` on a layout failure
    (ambiguous parent/child ``.atdd/`` or no Control Root found). The error is
    both logged (operational diagnostics) and printed (operator-facing CLI).
    """
    try:
        return resolve_control_root(start), 0
    except (AmbiguousControlRootError, ControlRootNotFoundError) as exc:
        _log.warning(
            "state layout resolution failed",
            extra={"start": str(start), "error": type(exc).__name__},
        )
        print(f"ERROR: {exc}")
        return None, 2


def _cmd_doctor(root: Optional[str]) -> int:
    start = _start_dir(root)
    print("ATDD State Store Doctor")
    resolution, rc = _resolve_or_report(start)
    if resolution is None:
        return rc

    gwr = resolution.git_worktree_root
    print(f"Control Root:       {resolution.control_root}")
    print(f"Git Worktree Root:  {gwr if gwr is not None else '(none — not in a git worktree)'}")
    print(f"Layout Mode:        {resolution.layout_mode.value}")
    print(f"State Store:        {resolution.state_store_path}")

    violations = check_layout(resolution.control_root)
    if violations:
        for v in violations:
            print(f"ERROR: {v}")
        print("Status:             INVALID")
        return 1
    if not resolution.state_store_exists:
        # Phase 1 does not create the store; this is informational, not a failure.
        print("Status:             OK (State Store not yet created — `atdd state init` lands in #1168 Phase 2)")
        return 0
    print("Status:             OK")
    return 0


def _cmd_layout_check(root: Optional[str]) -> int:
    start = _start_dir(root)
    resolution, rc = _resolve_or_report(start)
    if resolution is None:
        return rc

    violations = check_layout(resolution.control_root)
    if violations:
        for v in violations:
            print(f"ERROR: {v}")
        return 1
    print(f"Layout OK: {resolution.layout_mode.value} (Control Root: {resolution.control_root})")
    return 0


def run(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.op == "doctor":
        return _cmd_doctor(args.root)
    if args.op == "layout":
        if not args.check:
            parser.parse_args(["layout", "--help"])
            return 2
        return _cmd_layout_check(args.root)

    parser.print_help()
    return 2
