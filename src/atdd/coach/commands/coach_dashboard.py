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
        "--once",
        action="store_true",
        help="Print a single snapshot and exit (default on a TTY is the live view).",
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
    p.add_argument(
        "--no-color",
        action="store_true",
        dest="no_color",
        help="Disable phase colors (default: colored when stdout is a TTY).",
    )
    p.add_argument(
        "--card-width",
        type=int,
        default=40,
        dest="card_width",
        help="Card width in columns (default 40; wider fits full titles, fewer per row).",
    )
    return p


def _repo_slug() -> Optional[str]:
    """``owner/repo`` from the actual git remote (never inferred)."""
    import re
    import subprocess

    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", r.stdout.strip())
    return m.group(1) if m else None


def _load_titles(issues, runtime_dir: Path) -> dict:
    """Issue titles for the given numbers, cached at runtime/issue-titles.json.

    Titles are not in the worker JSON, so missing ones are fetched once via the
    GitHub REST API (core quota — not GraphQL) and cached. Best-effort: any
    failure leaves the title blank rather than breaking the render.
    """
    import json
    import subprocess

    cache = runtime_dir / "issue-titles.json"
    titles: dict = {}
    if cache.exists():
        try:
            titles = {int(k): v for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
        except (json.JSONDecodeError, OSError, ValueError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            titles = {}

    missing = [i for i in issues if i not in titles]
    if missing:
        repo = _repo_slug()
        for i in missing if repo else []:
            try:
                r = subprocess.run(
                    ["gh", "api", f"repos/{repo}/issues/{i}", "--jq", ".title"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0 and r.stdout.strip():
                    titles[i] = r.stdout.strip()
            except (OSError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
                pass
        try:
            cache.write_text(
                json.dumps({str(k): v for k, v in titles.items()}), encoding="utf-8"
            )
        except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            pass
    return titles


def _has_runs(runtime_dir: Path) -> bool:
    """True when a runtime dir holds at least one coach run."""
    runs = runtime_dir / "runs"
    try:
        return runs.is_dir() and any(runs.iterdir())
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return False


def _resolve_runtime_dir(default: Path) -> Path:
    """Find the coach's populated runtime.

    The coach centralizes every worker it spawns into one runtime (the primary
    worktree's ``.atdd/runtime``), not the per-worker checkouts. So when the
    current dir's runtime is empty, look across sibling worktrees and pick the
    one that actually has runs — letting ``atdd coach dashboard`` work from any
    worktree without ``ATDD_RUNTIME_DIR``.
    """
    if _has_runs(default):
        return default
    try:
        siblings = sorted(Path.cwd().parent.iterdir())
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return default
    candidates = [d / ".atdd" / "runtime" for d in siblings if d.is_dir()]
    populated = [rt for rt in candidates if _has_runs(rt)]
    if populated:
        return max(populated, key=lambda rt: sum(1 for _ in (rt / "runs").iterdir()))
    return default


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
                    phase=phase.upper() if isinstance(phase, str) else None,
                    agent_id=agent_id,
                    surface=s.get("cmux_surface") or "",
                    escalations=_read_escalations(runtime_dir / "agents" / agent_id),
                )
            )
    return workers


def _read_escalations(agent_dir: Path) -> list:
    """Per-worker channel events from agents/<id>/escalations.jsonl (chronological).

    Each record: {timestamp, severity, reason}. Returns [{ts, severity, reason}]
    with ts parsed to a datetime; build_cards formats + trims to the latest few.
    """
    import json

    path = agent_dir / "escalations.jsonl"
    if not path.exists():
        return []
    out: list = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            out.append({
                "ts": _parse_iso(r.get("timestamp")),
                "severity": r.get("severity", ""),
                "reason": r.get("reason", ""),
            })
    except (json.JSONDecodeError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return out
    return out


# Arrows arrive as CSI (ESC [ X, normal cursor mode) or SS3 (ESC O X,
# application cursor mode) — terminals switch between them, so handle both.
_ARROW_FINAL = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}


def _live_surfaces():
    """Set of surface refs currently open in cmux, or None if cmux is unavailable.

    None (cmux not queryable) makes the ``active`` filter fall back to run-roster
    membership rather than hiding every worker.
    """
    import json
    import subprocess

    try:
        r = subprocess.run(
            ["cmux", "tree", "--json"], capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return None

    surfaces: set = set()

    def _walk(node):
        if isinstance(node, dict):
            ref = node.get("ref")
            if isinstance(ref, str) and ref.startswith("surface:"):
                surfaces.add(ref)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(data)
    return surfaces or None


def _read_key(timeout: float):
    """Return a keypress within ``timeout`` seconds, or None (TTY only).

    Reads the raw fd (not buffered ``sys.stdin``, which can swallow keys). For an
    escape, it drains the whole sequence and matches the final byte — so arrows
    work whether the terminal sends CSI (``ESC [ C``), SS3 (``ESC O C``), or a
    modified form (``ESC [ 1 ; 2 C``). Plain keys return their character.
    """
    import os
    import select

    fd = sys.stdin.fileno()
    r, _, _ = select.select([fd], [], [], timeout)
    if not r:
        return None
    data = os.read(fd, 1)
    if data == b"\x1b":  # escape — drain the rest of the sequence
        seq = ""
        while True:
            more, _, _ = select.select([fd], [], [], 0.02)
            if not more or len(seq) >= 6:
                break
            seq += os.read(fd, 1).decode("latin-1", "ignore")
        if seq in ("[5~", "[6~"):
            return "PGUP" if seq == "[5~" else "PGDN"
        if seq and seq[-1] in _ARROW_FINAL:
            return _ARROW_FINAL[seq[-1]]
        return "\x1b"  # lone ESC / unhandled sequence
    return data.decode("utf-8", "ignore")


def _run_interactive(runtime_dir: Path, args) -> int:
    """Live, single-key-filterable dashboard. Requires a TTY stdin (cbreak mode).

    Gathers every worker once per refresh, then filters in-memory by the menu
    mode so a/h/b/s/p switch views instantly without re-reading the run scope.
    """
    import termios
    import tty

    from atdd.coach.runtime.dashboard import (
        PHASE_ORDER,
        build_cards,
        filter_cards,
        paginate,
        render_grid,
        render_menu,
    )
    from atdd.coach.runtime.reader import (
        derive_issue_phases,
        find_latest_run_id,
        read_decisions,
    )

    # ←/→ navigate the run-STATE; ↑/↓ cycle the PHASE sub-filter (0 = All).
    NAV_STATES = ["live", "stopped", "all"]
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    state, phase_idx, page, pages = "live", 0, 0, 1
    try:
        tty.setcbreak(fd)
        while True:
            run_id = args.run_id if args.run_id is not None else find_latest_run_id(runtime_dir)
            print("\033[2J\033[H", end="")
            if run_id is None:
                print(f"No coach runs found in {runtime_dir / 'coach'}")
            else:
                workers = _read_workers(runtime_dir, run_id, scope_all=True)
                issue_phases = derive_issue_phases(run_id, runtime_dir=runtime_dir)
                titles = _load_titles(
                    sorted({w.issue for w in workers if w.issue is not None}), runtime_dir
                )
                decisions = read_decisions(run_id, 50, runtime_dir=runtime_dir)
                # One cmux query per refresh: drives both liveness display
                # (up vs ran/ended) and the active filter.
                live = _live_surfaces()
                all_cards = build_cards(
                    agent_states=workers, issue_phases=issue_phases,
                    titles=titles, decisions=decisions, live_surfaces=live,
                )
                phase = PHASE_ORDER[phase_idx - 1] if phase_idx else None
                cards = filter_cards(all_cards, state, phase=phase)
                color = not args.no_color
                try:
                    rows = shutil.get_terminal_size((80, 24)).lines
                except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
                    rows = 24
                # Render the FULL grid, then page through it (variable-height cards),
                # so nothing below the fold is unreachable.
                grid = render_grid(
                    cards, _term_width(args.width), card_width=args.card_width, color=color
                )
                window, page, pages = paginate(grid.split("\n"), page, max(3, rows - 6))
                print(f"atdd coach dashboard · run {run_id} · {len(cards)}/{len(all_cards)} worker(s)")
                print(render_menu(state, phase=phase, color=color))
                hint = f"page {page + 1}/{pages} · SPACE/PgDn next · ←/→ state · ↑/↓ phase · q quit"
                print(f"\033[2m{hint}\033[0m" if color else hint)
                print()
                print("\n".join(window))
            key = _read_key(1.0)
            if key in ("q", "\x03"):
                break
            elif key in (" ", "PGDN"):
                page = (page + 1) % pages
            elif key == "PGUP":
                page = (page - 1) % pages
            elif key == "l":
                state, page = "live", 0
            elif key == "o":
                state, page = "stopped", 0
            elif key == "a":
                state, page = "all", 0
            elif key in ("RIGHT", "LEFT"):
                step = 1 if key == "RIGHT" else -1
                i = NAV_STATES.index(state) if state in NAV_STATES else (-1 if step == 1 else 0)
                state, page = NAV_STATES[(i + step) % len(NAV_STATES)], 0
            elif key in ("UP", "DOWN"):
                # Phase sub-filter cycles 0 (All) .. len(PHASE_ORDER); reset to page 1.
                phase_idx = (phase_idx + (1 if key == "UP" else -1)) % (len(PHASE_ORDER) + 1)
                page = 0
    except KeyboardInterrupt:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    return 0


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
        # Explicit env wins; otherwise auto-discover the coach's populated runtime.
        runtime_dir = Path(env_dir) if env_dir else _resolve_runtime_dir(Path(".atdd") / "runtime")

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
        issues = sorted({w.issue for w in workers if w.issue is not None})
        titles = _load_titles(issues, runtime_dir)

        cards = build_cards(
            agent_states=workers,
            issue_phases=issue_phases,
            titles=titles,
            decisions=decisions,
            live_surfaces=_live_surfaces(),
        )
        use_color = not args.no_color and sys.stdout.isatty()
        header = f"atdd coach dashboard · run {run_id} · {len(cards)} worker(s)"
        return header + "\n\n" + render_grid(
            cards, _term_width(args.width), card_width=args.card_width, color=use_color
        )

    # Live + interactive by default on a real terminal; a single snapshot when
    # piped/redirected (scriptable) or when --once is given.
    if not args.once and sys.stdin.isatty():
        return _run_interactive(runtime_dir, args)

    print(_render_once())
    return 0
