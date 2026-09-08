"""Renderer for `atdd coach status` — aligned table output and JSON mode.

Public surface:
- ``render_status_table(run_id, issue_phases, decisions, ...)`` — human table.
- ``render_status_json(run_id, issue_phases, decisions, ...)`` — JSON string.

Elapsed time is formatted by ``_format_hms``, inlined here in #1486 when the
observer (its previous home) was decommissioned.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from atdd.coach.runtime.reader import Decision, Judgment


def _format_hms(seconds: float) -> str:
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}"


def _elapsed(start_iso: Optional[str]) -> str:
    if not start_iso:
        return "unknown"
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = max(0.0, (now - start).total_seconds())
        return _format_hms(delta)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        return "unknown"


def _short_ts(ts: str) -> str:
    """Return HH:MM:SS portion of an ISO timestamp."""
    if "T" in ts:
        return ts.split("T")[1][:8]
    return ts[:8] if len(ts) >= 8 else ts


def render_status_table(
    run_id: str,
    issue_phases: dict[int, str],
    decisions: list[Decision],
    judgments: list[Judgment],
    *,
    start_ts: Optional[str] = None,
    sessions: Optional[list[dict]] = None,
) -> str:
    lines: list[str] = []
    elapsed = _elapsed(start_ts)

    lines.append("=" * 62)
    lines.append("atdd coach status")
    lines.append("=" * 62)
    lines.append(f"  Run ID : {run_id}")
    if start_ts:
        lines.append(f"  Started: {start_ts}")
    lines.append(f"  Elapsed: {elapsed}")
    lines.append("")

    if issue_phases:
        lines.append("Per-issue phases:")
        w_issue = max(len(str(k)) for k in issue_phases) + 1
        for issue_num, phase in sorted(issue_phases.items()):
            lines.append(f"  #{str(issue_num):<{w_issue}} {phase}")
        lines.append("")

    if decisions:
        lines.append("Recent decisions:")
        for d in decisions:
            ts = _short_ts(d.timestamp)
            lines.append(
                f"  [{ts}] issue=#{d.issue_number} type={d.decision_type}"
                + (f" id={d.decision_id}" if d.decision_id else "")
            )
        lines.append("")

    if judgments:
        lines.append("Recent judgments:")
        for j in judgments:
            ts = _short_ts(j.timestamp)
            cached_tag = " (cached)" if j.cached else ""
            lines.append(
                f"  [{ts}] site={j.call_site}{cached_tag}"
            )
        lines.append("")

    if sessions:
        lines.append("Agent sessions:")
        for s in sessions:
            agent_id = s.get("agent_id", "?")
            uuid = s.get("claude_resume_uuid", "?")
            lines.append(f"  {agent_id}: Resume agent: claude --resume {uuid}")
        lines.append("")

    return "\n".join(lines)


def render_status_json(
    run_id: Optional[str],
    issue_phases: dict[int, str],
    decisions: list[Decision],
    judgments: list[Judgment],
    *,
    start_ts: Optional[str] = None,
    sessions: Optional[list[dict]] = None,
) -> str:
    payload: dict = {
        "run_id": run_id,
        "started": start_ts,
        "issues": {str(k): v for k, v in sorted(issue_phases.items())},
        "sessions": sessions or [],
        "decisions": [
            {
                "decision_id": d.decision_id,
                "timestamp": d.timestamp,
                "issue_number": d.issue_number,
                "decision_type": d.decision_type,
                "outcome": d.outcome,
            }
            for d in decisions
        ],
        "judgments": [
            {
                "judgment_id": j.judgment_id,
                "timestamp": j.timestamp,
                "call_site": j.call_site,
                "cached": j.cached,
                "outcome": j.outcome,
            }
            for j in judgments
        ],
    }
    return json.dumps(payload, indent=2)
