"""``atdd.observer`` — first-class READ-ONLY consumer (Coach Decomposition §8).

The observer reads two single-writer artifacts and **never writes to either**:

- ``events.jsonl`` — single writer is the train runner (``atdd.train.persistence``),
  one per run under ``.atdd/runtime/runs/<run_id>/`` (§5.1, §5.2).
- per-agent ``output.log`` — single writer is ``atdd.runtime.agent_control``.

It surfaces a live stream in the CLI and aggregates across active runs.

Dependency posture (§3.3): this layer imports **stdlib only**. It opens every
file in read mode (``"r"``); there is no code path anywhere in this module that
opens ``events.jsonl`` or ``output.log`` for writing. That import-cleanliness is
what lets the observer be a true passive consumer — it can be pointed at a live
run without any risk of corrupting the single-writer invariant.

Promoted to first-class in Child 10 (#897); previously observer launch/lifecycle
was scattered as a coach side-effect.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar, Iterator, Optional

__all__ = [
    "RUNS_REL",
    "ObserverAlreadyRunningError",
    "ObserverSession",
    "runs_root",
    "list_run_ids",
    "read_events",
    "aggregate_events",
    "tail_output_log",
    "render_stream",
    "run",
]

#: Runs live under ``<repo_root>/.atdd/runtime/runs/<run_id>/`` (§5.1).
RUNS_REL = Path(".atdd/runtime/runs")

#: Filename of the per-run, single-writer event log (§5.2).
EVENTS_FILE = "events.jsonl"

#: Filename of the per-agent, single-writer stdout capture.
OUTPUT_LOG = "output.log"


class ObserverAlreadyRunningError(RuntimeError):
    """Raised when a second observer session starts while one is already active.

    Incident defense I-6 (single observer lifecycle): the observer is a
    singleton so two consumers can never disagree about — or race on — the
    surfaced stream.
    """


# --------------------------------------------------------------------------- #
# read-only readers (stdlib only; every open is read mode)
# --------------------------------------------------------------------------- #
def runs_root(repo_root: Path) -> Path:
    return Path(repo_root) / RUNS_REL


def list_run_ids(repo_root: Path) -> list[str]:
    """Every run directory under ``.atdd/runtime/runs/`` (sorted, read-only)."""
    root = runs_root(repo_root)
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


def read_events(repo_root: Path, run_id: str) -> list[dict]:
    """Parse one run's ``events.jsonl`` (READ-ONLY). Missing file → ``[]``."""
    path = runs_root(repo_root) / run_id / EVENTS_FILE
    if not path.is_file():
        return []
    events: list[dict] = []
    # Read mode only — the observer is never a writer to events.jsonl.
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                # A partial trailing line (writer mid-append) is skipped, not
                # repaired — the observer never mutates the file.
                continue
    return events


def aggregate_events(repo_root: Path) -> list[dict]:
    """All events across all runs, each tagged with its ``run_id``.

    Ordered by ``(run_id, seq)`` so a multi-run view is stable and replayable.
    """
    out: list[dict] = []
    for run_id in list_run_ids(repo_root):
        for ev in read_events(repo_root, run_id):
            tagged = dict(ev)
            tagged.setdefault("run_id", run_id)
            out.append(tagged)
    out.sort(key=lambda e: (str(e.get("run_id", "")), int(e.get("seq", 0))))
    return out


def tail_output_log(path: Path, *, limit: Optional[int] = None) -> list[str]:
    """Return the last ``limit`` lines of a per-agent ``output.log`` (READ-ONLY)."""
    path = Path(path)
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        lines = [ln.rstrip("\n") for ln in fh]
    return lines if limit is None else lines[-limit:]


def iter_output_log(path: Path) -> Iterator[str]:
    """Stream a per-agent ``output.log`` line-by-line (READ-ONLY)."""
    path = Path(path)
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            yield line.rstrip("\n")


# --------------------------------------------------------------------------- #
# singleton session (I-6)
# --------------------------------------------------------------------------- #
class ObserverSession:
    """A single read-only observation session over one repo's runs.

    Enforces the single-observer lifecycle (I-6): only one session may be
    ``start()``-ed at a time within a process. ``stop()`` (or the context
    manager exit) releases the slot. The session itself holds no writers.
    """

    _active: ClassVar[Optional["ObserverSession"]] = None

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)
        self._started = False

    def start(self) -> "ObserverSession":
        if ObserverSession._active is not None and ObserverSession._active is not self:
            raise ObserverAlreadyRunningError(
                "another ObserverSession is already active; the observer is a "
                "singleton (incident defense I-6)"
            )
        ObserverSession._active = self
        self._started = True
        return self

    def stop(self) -> None:
        if ObserverSession._active is self:
            ObserverSession._active = None
        self._started = False

    def snapshot(self) -> list[dict]:
        """Current aggregated event stream (READ-ONLY)."""
        return aggregate_events(self.repo_root)

    def __enter__(self) -> "ObserverSession":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


# --------------------------------------------------------------------------- #
# CLI surface — `atdd observer view`
# --------------------------------------------------------------------------- #
def render_stream(repo_root: Path, *, limit: Optional[int] = None) -> str:
    """Render the aggregated event stream as text (READ-ONLY)."""
    events = aggregate_events(repo_root)
    if limit is not None:
        events = events[-limit:]
    if not events:
        return "(no events)"
    lines = []
    for ev in events:
        run_id = ev.get("run_id", "?")
        seq = ev.get("seq", "?")
        etype = ev.get("event_type") or ev.get("type") or "event"
        ts = ev.get("timestamp", "")
        lines.append(f"{run_id} #{seq} {etype} {ts}".rstrip())
    return "\n".join(lines)


def run(argv: Optional[list[str]] = None) -> int:
    """``atdd observer view`` — print the read-only aggregated stream and exit."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="atdd observer view",
        description="Read-only live view of train events.jsonl + agent output.log (§8).",
    )
    parser.add_argument("--repo-root", default=".", help="Repo root (default: cwd)")
    parser.add_argument("--limit", type=int, default=None, help="Show only the last N events")
    parser.add_argument("--output-log", default=None,
                        help="Also tail this per-agent output.log (read-only)")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root)
    with ObserverSession(repo_root):  # singleton lifecycle (I-6)
        print(render_stream(repo_root, limit=args.limit))
        if args.output_log:
            print("--- output.log ---")
            for line in tail_output_log(Path(args.output_log), limit=args.limit):
                print(line)
    return 0
