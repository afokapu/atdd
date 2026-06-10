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
STALL_AFTER_SECONDS = 10 * 60

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


def _colorize(text: str, rgb: tuple) -> str:
    r, g, b = rgb
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m"


def _progress_bar(phase: str) -> str:
    """A filled/unfilled lifecycle bar for ``phase`` (e.g. ``▰▰▰▰▱▱▱ 4/7``)."""
    total = len(PHASE_ORDER)
    if phase in PHASE_ORDER:
        filled = PHASE_ORDER.index(phase) + 1
        return "▰" * filled + "▱" * (total - filled) + f" {filled}/{total}"
    if phase in ("BLOCKED", "OBSOLETE"):
        return "▱" * total + " ✗"
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
    elapsed: str
    tasks: list[Task] = field(default_factory=list)
    stalled: bool = False

    @property
    def done_count(self) -> int:
        return sum(1 for t in self.tasks if t.state == "done")


def _elapsed(start: Optional[datetime], now: datetime) -> str:
    """Human ``HhMm`` / ``MmSs`` elapsed from ``start`` to ``now``."""
    if start is None:
        return "--"
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    secs = max(0, int((now - start).total_seconds()))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


def _seconds_since(start: Optional[datetime], now: datetime) -> Optional[int]:
    if start is None:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return max(0, int((now - start).total_seconds()))


def build_cards(
    *,
    agent_states: Sequence,
    issue_phases: dict[int, str],
    titles: Optional[dict[int, str]] = None,
    decisions: Optional[Iterable] = None,
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
        # Elapsed is true runtime (since spawn); stall is measured from last
        # activity. When no spawn time is known, fall back to last activity.
        start = getattr(st, "started_at", None) or last
        secs = _seconds_since(last, now)
        cards.append(
            WorkerCard(
                issue=issue,
                title=titles.get(int(issue), "") if issue is not None else "",
                phase=phase,
                role=role,
                elapsed=_elapsed(start, now),
                tasks=list(activity.get(int(issue), [])) if issue is not None else [],
                stalled=secs is not None and secs > STALL_AFTER_SECONDS,
            )
        )
    # Stable ordering: stalled first (they need attention), then by issue.
    cards.sort(key=lambda c: (not c.stalled, c.issue if c.issue is not None else 1 << 30))
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
    flag = " ⚠" if card.stalled else ""

    lines = [top, row(f"{num}  {card.phase}", paint=True)]
    if card.title:
        lines.append(row(card.title))
    pbar = _progress_bar(card.phase)
    if pbar:
        lines.append(row(pbar, paint=True))
    lines.append(row(f"{card.role} · {card.elapsed}{flag}"))
    if card.tasks:
        lines.append(row(""))
        for t in card.tasks[:4]:
            glyph = _TASK_GLYPH.get(t.state, "○")
            lines.append(row(f"{glyph} {t.text}"))
        total = len(card.tasks)
        lines.append(row(f" {card.done_count}/{total} ".center(inner, "─")))
    lines.append(bottom)
    return lines


def render_grid(
    cards: Sequence[WorkerCard], term_width: int, *, card_width: int = 21, color: bool = False
) -> str:
    """Lay cards out in a reflowing grid that fits ``term_width``.

    Columns are chosen from the available width; cards in a row are padded to
    equal height so the grid stays aligned.
    """
    if not cards:
        return "No active workers."

    gutter = 1
    cols = max(1, (term_width + gutter) // (card_width + gutter))
    blocks = [render_card(c, card_width, color=color) for c in cards]

    out: list[str] = []
    for i in range(0, len(blocks), cols):
        rowcards = blocks[i : i + cols]
        height = max(len(b) for b in rowcards)
        pad = " " * card_width
        for b in rowcards:
            b.extend([pad] * (height - len(b)))
        for r in range(height):
            out.append((" " * gutter).join(b[r] for b in rowcards))
    return "\n".join(out)
