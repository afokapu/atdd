"""Worker-grid renderer for ``atdd coach dashboard``.

A third renderer over the same reader layer that backs ``atdd coach status``
(see :mod:`atdd.coach.runtime.reader`). Where ``status`` prints a single
aligned table, ``dashboard`` lays out one card per active worker in a reflowing
grid, so an operator watching many workers at once can spot the one that needs
attention.

Design notes
------------
* **Stdlib only.** The card grid is plain ANSI box-drawing, matching the
  hand-rolled ``--watch`` loop in :mod:`atdd.coach.commands.coach_status`. No
  ``rich``/``textual`` dependency is added to the dependency-light CLI.
* **Pure core.** ``build_cards`` and ``render_grid`` are side-effect-free
  transforms (data in, string out) so they unit-test without a TTY, a clock,
  or GitHub. I/O and the refresh loop live in the command layer.
* **Per worker, not per issue.** One card per agent; the same issue can appear
  twice (e.g. a ``coder`` and a ``tester`` card for one issue).

The per-card task list (TodoWrite items) is a documented follow-up: it is
modelled here (``WorkerCard.tasks``) and rendered when present, but wiring it to
the live ``cmux events`` agent-hook stream is deferred to a later step on this
issue. ``build_cards`` populates a best-effort activity list from coach
decisions so the field is never empty in the meantime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

# Workers with no heartbeat for longer than this are flagged as stalled. Matches
# the operator drift threshold: >10 min with no progress warrants intervention.
# A running worker with no activity for this long flips from "live" to "paused".
PAUSE_AFTER_SECONDS = 10 * 60

_TASK_GLYPH = {"done": "✓", "doing": "◐", "todo": "○"}

# Canonical lifecycle progression (escapes BLOCKED/OBSOLETE are off-track), from
# src/atdd/coach/conventions/phase_machine.convention.yaml — drives the per-card
# progress bar.
PHASE_ORDER = ["INIT", "PLANNED", "RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"]

# Per-phase truecolor, matching the GitHub `atdd:<PHASE>` issue-label colors so
# the dashboard reads the same as the GitHub board.
PHASE_RGB = {
    "INIT": (0xFB, 0xCA, 0x04),
    "PLANNED": (0xB6, 0x02, 0x05),
    "RED": (0xD9, 0x3F, 0x0B),
    "GREEN": (0x0E, 0x8A, 0x16),
    "SMOKE": (0x1D, 0x76, 0xDB),
    "REFACTOR": (0x00, 0x6B, 0x75),
    "COMPLETE": (0x6F, 0x42, 0xC1),
    "BLOCKED": (0xD7, 0x3A, 0x4A),
    "OBSOLETE": (0x6A, 0x73, 0x7D),
}


# Channel-event severity → truecolor (block = red, warn = amber).
_SEVERITY_RGB = {
    "block": (0xD7, 0x3A, 0x4A),
    "error": (0xD7, 0x3A, 0x4A),
    "warn": (0xFB, 0xCA, 0x04),
    "warning": (0xFB, 0xCA, 0x04),
}


def _colorize(text: str, rgb: tuple) -> str:
    r, g, b = rgb
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m"


_BAR_CELLS_PER_PHASE = 3


def _progress_bar(phase: str, cells_per_phase: int = _BAR_CELLS_PER_PHASE) -> str:
    """A filled/unfilled lifecycle bar for ``phase`` — ``cells_per_phase`` cells
    per stage (e.g. ``▰▰▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱`` for GREEN at 3 cells/phase)."""
    total = len(PHASE_ORDER) * cells_per_phase
    if phase in PHASE_ORDER:
        filled = (PHASE_ORDER.index(phase) + 1) * cells_per_phase
        return "▰" * filled + "▱" * (total - filled)
    if phase in ("BLOCKED", "OBSOLETE"):
        return "▱" * total
    return ""  # unknown phase → no bar


@dataclass
class Task:
    """One item in a worker's task list."""

    text: str
    state: str = "todo"  # one of: done | doing | todo


@dataclass
class Worker:
    """A live worker as gathered from ``.atdd/runtime/agents/<id>/``.

    Sourced from ``manifest.json`` (``issue``/``persona``) and the tail of
    ``events.jsonl`` (last activity → elapsed + stall detection). Duck-typed by
    :func:`build_cards`, which reads ``issue``/``phase``/``role``/
    ``last_heartbeat`` off whatever worker object it is handed.
    """

    issue: Optional[int]
    role: str
    last_heartbeat: Optional[datetime] = None
    phase: Optional[str] = None
    agent_id: str = ""
    started_at: Optional[datetime] = None
    surface: str = ""  # cmux surface ref, e.g. "surface:623"
    escalations: list = field(default_factory=list)  # raw [{ts, severity, reason}], recent last


@dataclass
class WorkerCard:
    """Everything one rectangle in the grid renders.

    Fields map directly to the operator's requested card contents: issue
    number, issue title, current phase, task list, and elapsed run time.
    """

    issue: Optional[int]
    title: str
    phase: str
    role: str
    started: str = ""  # absolute spawn clock time (HH:MM, or "Mon D HH:MM")
    last: str = ""  # absolute time of the most recent channel event (blank if none)
    surface: str = ""  # cmux surface ref — distinguishes workers on the same issue
    state: str = "live"  # "live" (surface open) | "stopped" (surface closed)
    events: list = field(default_factory=list)  # recent channel events (Event), newest first
    tasks: list[Task] = field(default_factory=list)


@dataclass
class Event:
    """One per-worker channel event (an observer escalation), for the card feed."""

    time: str  # absolute clock time
    severity: str  # e.g. block | warn
    text: str  # human-readable reason

    @property
    def done_count(self) -> int:
        return sum(1 for t in self.tasks if t.state == "done")


def _fmt_secs(secs: Optional[int]) -> str:
    """Human ``DdHh`` / ``HhMm`` / ``MmSs`` duration from a second count."""
    if secs is None:
        return "--"
    secs = max(0, int(secs))
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    if d:
        return f"{d}d{h:02d}h"
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


def _fmt_clock(dt: Optional[datetime], now: datetime) -> str:
    """Absolute clock time (not a 'time since'): ``HH:MM`` today, else ``Mon D HH:MM``.

    Rendered in local time. Stable to test because it derives only from the
    given ``dt`` and the injected ``now`` — no wall-clock read.
    """
    if dt is None:
        return "?"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone()
    today = (now if now.tzinfo else now.replace(tzinfo=timezone.utc)).astimezone().date()
    if local.date() == today:
        return local.strftime("%H:%M")
    return f"{local.strftime('%b')} {local.day} {local.strftime('%H:%M')}"


def _elapsed(start: Optional[datetime], now: datetime) -> str:
    """Human elapsed from ``start`` to ``now``."""
    if start is None:
        return "--"
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return _fmt_secs(int((now - start).total_seconds()))


def _seconds_since(start: Optional[datetime], now: datetime) -> Optional[int]:
    if start is None:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return max(0, int((now - start).total_seconds()))


def _duration_secs(
    start: Optional[datetime], last: Optional[datetime], now: datetime
) -> Optional[int]:
    """Active run duration: last activity − spawn (NOT wall-clock since spawn).

    A worker that ran 30 min two days ago reads as 30m, not 48h. For a still-live
    worker (last ≈ now) this is the ongoing duration. With no spawn time, falls
    back to time since last activity.
    """
    if start is None:
        return _seconds_since(last, now)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    end = last if last is not None else now
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0, int((end - start).total_seconds()))


def build_cards(
    *,
    agent_states: Sequence,
    issue_phases: dict[int, str],
    titles: Optional[dict[int, str]] = None,
    decisions: Optional[Iterable] = None,
    live_surfaces: Optional[set] = None,
    now: Optional[datetime] = None,
) -> list[WorkerCard]:
    """Transform reader output into renderable cards.

    Pure: no I/O, no wall-clock read (``now`` is injected). ``agent_states`` is
    a sequence of :class:`atdd.coach.runtime.reader.AgentState`; ``decisions``
    an optional iterable of :class:`~atdd.coach.runtime.reader.Decision` used to
    seed a best-effort activity list per issue until live TodoWrite wiring
    lands.
    """
    now = now or datetime.now(timezone.utc)
    titles = titles or {}

    # Best-effort per-issue activity from coach decisions (placeholder for the
    # real TodoWrite task list).
    activity: dict[int, list[Task]] = {}
    for d in decisions or []:
        issue = getattr(d, "issue_number", None)
        if issue is None:
            continue
        label = getattr(d, "decision_type", "") or "decision"
        activity.setdefault(int(issue), []).append(Task(text=label, state="done"))

    cards: list[WorkerCard] = []
    for st in agent_states:
        issue = getattr(st, "issue", None)
        phase = getattr(st, "phase", None) or (
            issue_phases.get(int(issue)) if issue is not None else None
        ) or "?"
        role = _role_of(st)
        last = getattr(st, "last_heartbeat", None)
        start = getattr(st, "started_at", None)
        surface = getattr(st, "surface", "") or ""
        # State from the cmux surface only: open → live, known-closed → stopped.
        # (The observer heartbeat is a continuous ping, not activity, so it can't
        # tell us idle/paused — we don't guess it.)
        known_closed = live_surfaces is not None and bool(surface) and surface not in live_surfaces
        state = "stopped" if known_closed else "live"
        # Channel events (observer escalations) — the only real per-worker channel
        # signal. Newest first; `last` is the most recent event's time.
        raw = getattr(st, "escalations", []) or []
        events = [
            Event(time=_fmt_clock(e.get("ts"), now), severity=str(e.get("severity", "")),
                  text=str(e.get("reason", "")))
            for e in reversed(raw[-3:])
        ]
        cards.append(
            WorkerCard(
                issue=issue,
                title=titles.get(int(issue), "") if issue is not None else "",
                phase=phase,
                role=role,
                started=_fmt_clock(start, now),
                last=events[0].time if events else "",
                surface=surface,
                state=state,
                events=events,
                tasks=list(activity.get(int(issue), [])) if issue is not None else [],
            )
        )
    # Order by lifecycle phase (INIT→…→REFACTOR) so the grid reads in pipeline
    # order, then by issue and surface for stability.
    cards.sort(
        key=lambda c: (
            PHASE_ORDER.index(c.phase) if c.phase in PHASE_ORDER else len(PHASE_ORDER),
            c.issue if c.issue is not None else 1 << 30,
            c.surface,
        )
    )
    return cards


def _role_of(state) -> str:
    """Best-effort role for a worker (coder/tester/planner/...)."""
    role = getattr(state, "role", None)
    if role:
        return str(role)
    agent_id = getattr(state, "agent_id", "") or ""
    # agent ids commonly encode the role as the trailing token.
    for sep in ("·", ":", "-", "_"):
        if sep in agent_id:
            return agent_id.rsplit(sep, 1)[-1]
    return agent_id or "?"


def _truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


def render_card(card: WorkerCard, width: int, *, color: bool = False) -> list[str]:
    """Render one card as a list of ``width``-wide lines (ANSI box-drawing).

    When ``color`` is set, the border, phase header, and progress bar are tinted
    in the phase's GitHub-label color. Color codes wrap already-padded content,
    so the *visible* width stays exactly ``width`` regardless of tinting.
    """
    inner = max(1, width - 2)
    rgb = PHASE_RGB.get(card.phase) if color else None

    def tint(s: str) -> str:
        return _colorize(s, rgb) if rgb else s

    def row(content: str, *, paint: bool = False) -> str:
        body = _truncate(content, inner).ljust(inner)
        return tint("│") + (tint(body) if paint else body) + tint("│")

    top = tint("┌" + "─" * inner + "┐")
    bottom = tint("└" + "─" * inner + "┘")

    num = f"#{card.issue}" if card.issue is not None else "#?"

    # Paused flag rides the header so it's prominent and never truncated by a
    # narrow card; the meta line carries the durations.
    head = f"{num}  {card.phase}" + (" ⚠" if card.state == "paused" else "")
    lines = [top, row(head, paint=True)]
    if card.title:
        lines.append(row(card.title))
    pbar = _progress_bar(card.phase)
    if pbar:
        lines.append(row(pbar, paint=True))
    # 'persona (surface)' distinguishes workers on the same issue. A LIVE worker
    # shows uptime ('up'); a FINISHED worker (surface closed) shows its run
    # duration and when it ended — 'uptime' is meaningless for a dead worker.
    surf = card.surface.split(":")[-1] if card.surface else ""
    who = f"{card.role}" + (f" ({surf})" if surf else "")
    # Absolute spawn time + surface-derived state; no growing counters.
    lines.append(row(f"{who} · started {card.started} · {card.state}"))
    # Channel events feed (observer escalations), newest first, severity-tinted.
    if card.events:
        lines.append(row("─ channel ".ljust(inner, "─")))
        for ev in card.events:
            rgb = _SEVERITY_RGB.get(ev.severity) if color else None
            label = f"⚠ {ev.time} {ev.severity}: " if ev.severity else f"· {ev.time} "
            body = _truncate(label + ev.text, inner).ljust(inner)
            painted = _colorize(body, rgb) if rgb else body
            lines.append(tint("│") + painted + tint("│"))
    lines.append(bottom)
    return lines


# Single-key filter menu. Each entry: (key, mode, label). 'quit' is an action,
# not a filter mode. Kept deliberately small to stay glanceable.
# Primary run-state filters. Phase is a separate, orthogonal sub-filter.
STATE_KEYS = [
    ("l", "live", "Live"),
    ("o", "stopped", "Stopped"),
    ("a", "all", "All"),
]


def filter_cards(
    cards: Sequence[WorkerCard],
    state: str,
    *,
    phase: Optional[str] = None,
) -> list[WorkerCard]:
    """Filter by run ``state`` (live/paused/stopped/all) and an optional ``phase``.

    State and phase are orthogonal: when both are given, both apply (e.g.
    Live + RED). ``state="all"`` keeps every state; ``phase=None`` keeps every
    phase.
    """
    out = list(cards)
    if state in ("live", "stopped"):
        out = [c for c in out if c.state == state]
    if phase:
        out = [c for c in out if c.phase == phase]
    return out


def render_menu(state: str, *, phase: Optional[str] = None, color: bool = True) -> str:
    """Two-axis menu: a State row (highlighted) and a Phase sub-filter row."""

    def hi(seg: str, on: bool) -> str:
        if not on:
            return seg
        return f"\033[7m {seg} \033[0m" if color else f"▸{seg}◂"

    states = "  ".join(hi(f"[{k}] {label}", name == state) for k, name, label in STATE_KEYS)
    return f"State: {states}   [q] Quit\nPhase: {phase or 'All'}  (↑/↓)"


def render_grid(
    cards: Sequence[WorkerCard],
    term_width: int,
    *,
    card_width: int = 21,
    color: bool = False,
    max_lines: Optional[int] = None,
) -> str:
    """Lay cards out in a reflowing grid that fits ``term_width``.

    Columns are chosen from the available width; cards in a row are padded to
    equal height so the grid stays aligned. When ``max_lines`` is set, the grid
    is clamped to that many lines (whole card-rows only) and a ``+N more`` footer
    is appended — so a fixed header/menu above it never scrolls off-screen.
    """
    if not cards:
        return "No active workers."

    gutter = 1
    cols = max(1, (term_width + gutter) // (card_width + gutter))
    blocks = [render_card(c, card_width, color=color) for c in cards]

    out: list[str] = []
    shown = 0
    for i in range(0, len(blocks), cols):
        rowcards = blocks[i : i + cols]
        height = max(len(b) for b in rowcards)
        pad = " " * card_width
        for b in rowcards:
            b.extend([pad] * (height - len(b)))
        rowlines = [(" " * gutter).join(b[r] for b in rowcards) for r in range(height)]
        # Reserve one line for the footer; clamp on whole card-rows.
        if max_lines is not None and len(out) + len(rowlines) + 1 > max_lines:
            out.append(f"… +{len(cards) - shown} more — filter to narrow (b/s/p)")
            break
        out.extend(rowlines)
        shown += len(rowcards)
    return "\n".join(out)
