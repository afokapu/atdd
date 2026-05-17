"""`atdd coach` workspace layout — single canonical tab + consolidated view.

Public surface (re-exported from ``coach.py`` so existing importers are
unaffected — mirrors the ``coach_status`` / ``coach_review`` / ``coach_watch``
/ ``coach_gc`` extraction pattern):

  ``resolve_or_create_coach_surface(mx, config, issue_number=None)``
  ``build_consolidated_view(records)``
  ``render_consolidated_view(mx, config, records)``
  ``add_worker_surface(mx, worker_name, *, config=None)``

Issue #736: N coach invocations (or one coach driving N issues) used to open
N ``ATDD-coach-<N>`` terminal tabs, and every worker opened a new tiled pane
that shrank the coach's half. This module gives the coach a single canonical
``<REPO>-coach`` orchestration surface, renders a consolidated per-issue
status view into it, and places workers as right-pane surfaces — so the coach
workspace stays readable and singular regardless of how many issues or
workers are in flight.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from atdd.coach.utils.session_naming import compute_coach_surface_name

__all__ = [
    "resolve_or_create_coach_surface",
    "build_consolidated_view",
    "render_consolidated_view",
    "add_worker_surface",
]


def resolve_or_create_coach_surface(
    multiplexer: Any,
    config: Optional[Dict[str, Any]],
    issue_number: Optional[int] = None,
) -> str:
    """Resolve-or-create the singular canonical coach orchestration surface.

    N coach invocations (or one coach driving N issues) must resolve to ONE
    tab. The first call creates the ``<REPO>-coach`` surface; every later call
    finds and returns it. ``issue_number`` is accepted for issue-context
    callers and ignored — the canonical coach surface is issue-number-free.
    """
    name = compute_coach_surface_name(config, issue_number)
    for pane in multiplexer.list_panes():
        if pane.get("name") == name:
            return pane["ref"]
    return multiplexer.new_workspace(name=name)


def build_consolidated_view(records: List[Dict[str, Any]]) -> str:
    """Render the consolidated multi-issue coach status view.

    Emits one status row per managed issue — phase, last decision, and
    worker/agent health — so an operator reads overall orchestration state at
    a glance instead of one raw coach process terminal per invocation.
    """
    lines = [f"Consolidated coach view — {len(records)} issue(s)"]
    for rec in records:
        lines.append(
            f"  #{rec['issue']}  "
            f"phase={rec['phase']}  "
            f"last-decision={rec['last_decision']}  "
            f"worker-health={rec['worker_health']}"
        )
    return "\n".join(lines)


def render_consolidated_view(
    multiplexer: Any,
    config: Optional[Dict[str, Any]],
    records: List[Dict[str, Any]],
) -> str:
    """Render the consolidated view into the canonical coach surface.

    Resolves-or-creates the singular coach tab and sends the multi-issue
    status view into it — no new surface is created to host the view.
    Returns the surface ref the view was rendered into.
    """
    surface_ref = resolve_or_create_coach_surface(multiplexer, config)
    multiplexer.send(surface_ref, build_consolidated_view(records))
    return surface_ref


def add_worker_surface(
    multiplexer: Any,
    worker_name: str,
    *,
    config: Optional[Dict[str, Any]] = None,
) -> str:
    """Place a worker as a surface in the coach workspace's right pane.

    A worker is a surface (tab), never a new tiled pane: a new pane re-tiles
    the workspace and shrinks the coach's half, whereas a surface costs zero
    space. Returns the new surface ref.
    """
    return multiplexer.new_surface(name=worker_name)
