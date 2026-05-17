"""`atdd coach gc` — retroactive orphan-pane garbage collection.

Public surface:
  ``run_gc(argv)`` — entry point called by ``coach.run_cli``.

Every failed or partial ``atdd coach`` spawn used to strand a cmux pane
that defaulted its title to its fallback cwd (``~/Github/atdd``) and never
got reclaimed (#655). The transactional spawn pipeline now prevents *new*
leaks; this command retroactively cleans up the ones already accumulated.

It reconciles live cmux surfaces in a workspace against the surface refs
recorded in ``.atdd/runtime/coach/*/decisions.jsonl``. A pane is an orphan
when its panel label is the default ``~/Github/atdd`` cwd AND no decision
references its surface. Conservative by default: ``--dry-run`` lists the
orphans, ``--apply`` closes them.

CLI examples::

    atdd coach gc                       # list orphan panes (dry-run, default)
    atdd coach gc --dry-run             # same — explicit
    atdd coach gc --apply               # close the detected orphan panes
    atdd coach gc --workspace workspace:2   # target a non-default workspace

Real cmux contract (cmux 0.63.2, verified #655 SMOKE):
  ``cmux list-panels --workspace <ws>`` emits one line per surface::

      * surface:511  terminal  [focused]  "/work/feat-x"
        surface:512  terminal  "~/Github/atdd"

  i.e. ``[*| ] surface:N  <type>  [<flags>...]  "<label>"`` — the cwd/title
  is a quoted trailing string, NOT a ``cwd:<path>`` token.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

_SURFACE_RE = re.compile(r"\bsurface:\d+\b")
# The panel label (cwd / title) is the quoted trailing string on the line.
_LABEL_RE = re.compile(r'"([^"]*)"')


def _build_gc_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="atdd coach gc",
        description=(
            "Detect and clean up orphan cmux panes left by failed or partial "
            "coach spawns."
        ),
    )
    p.add_argument(
        "--workspace",
        default="workspace:1",
        metavar="REF",
        help="cmux workspace to reconcile (default: workspace:1).",
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        help="List orphan panes without closing them (default).",
    )
    group.add_argument(
        "--apply",
        action="store_true",
        help="Close the detected orphan panes.",
    )
    return p


def _resolve_repo_root() -> Path:
    """Locate the repo root without the cached find_repo_root().

    Honours ATDD_REPO_ROOT, otherwise walks up from cwd for a ``.atdd``
    directory. Uncached so it stays correct across successive calls.
    """
    env = os.environ.get("ATDD_REPO_ROOT")
    if env:
        env_path = Path(env).resolve()
        if env_path.is_dir():
            return env_path
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".atdd").is_dir():
            return current
        current = current.parent
    return Path.cwd().resolve()


def _extract_surface_ref(record: dict) -> Optional[str]:
    """Pull the spawned surface ref out of a decisions.jsonl record."""
    outcome = record.get("outcome")
    if isinstance(outcome, dict) and isinstance(outcome.get("surface_ref"), str):
        return outcome["surface_ref"]
    if isinstance(record.get("surface_ref"), str):
        return record["surface_ref"]
    return None


def _referenced_surface_refs(repo_root: Path) -> set[str]:
    """Surface refs recorded by every coach decision log under the repo."""
    refs: set[str] = set()
    coach_dir = repo_root / ".atdd" / "runtime" / "coach"
    if not coach_dir.is_dir():
        return refs
    logs = list(coach_dir.glob("*/decisions.jsonl")) + list(
        coach_dir.glob("decisions.jsonl")
    )
    for log in logs:
        try:
            text = log.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            ref = _extract_surface_ref(record)
            if ref:
                refs.add(ref)
    return refs


def _is_default_cwd(label: Optional[str]) -> bool:
    """A pane carries the default fallback cwd (~/Github/atdd) when its seed
    command never ran — its panel label is the bare repo path rather than a
    canonical session name or worktree path. Conservative: an unknown label
    is NOT treated as default.
    """
    if not label:
        return False
    return label.rstrip("/").endswith("Github/atdd")


def _list_panes(workspace: str) -> list[dict]:
    """Live panes in ``workspace``, parsed from real ``cmux list-panels``.

    Each line is ``[*| ] surface:N  <type>  [<flags>...]  "<label>"`` — the
    label (cwd / title) is the quoted trailing string.
    """
    result = None
    try:
        result = subprocess.run(
            ["cmux", "list-panels", "--workspace", workspace],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        # cmux is not installed — observably report and fall through; the
        # return happens outside the handler (coder.logging.coach-silent-swallow).
        print("atdd coach gc: cmux not found — nothing to reconcile.", file=sys.stderr)
    if result is None:
        return []
    panes: list[dict] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = _SURFACE_RE.search(line)
        if not match:
            continue
        labels = _LABEL_RE.findall(line)
        panes.append(
            {"surface_ref": match.group(0), "cwd": labels[-1] if labels else None}
        )
    return panes


def run_gc(argv: list[str]) -> int:
    """Entry point for ``atdd coach gc`` — forwarded from coach.run_cli."""
    args = _build_gc_parser().parse_args(argv)
    apply = bool(args.apply)
    workspace = args.workspace

    repo_root = _resolve_repo_root()
    referenced = _referenced_surface_refs(repo_root)
    orphans = [
        pane
        for pane in _list_panes(workspace)
        if pane["surface_ref"] not in referenced and _is_default_cwd(pane["cwd"])
    ]

    if not orphans:
        print(f"atdd coach gc: no orphan panes found in {workspace}.")
        return 0

    verb = "closing" if apply else "found"
    print(f"atdd coach gc: {verb} {len(orphans)} orphan pane(s) in {workspace}:")
    for pane in orphans:
        print(f"  {pane['surface_ref']}  (cwd: {pane['cwd']})")

    if not apply:
        print("Run `atdd coach gc --apply` to close them.")
        return 0

    for pane in orphans:
        # Scope the surface ref to its workspace — cmux resolves short
        # `surface:` refs against the selected workspace only (#655).
        subprocess.run(
            [
                "cmux", "close-surface",
                "--surface", pane["surface_ref"],
                "--workspace", workspace,
            ],
            capture_output=True,
            text=True,
        )
    print(f"atdd coach gc: closed {len(orphans)} orphan pane(s).")
    return 0
