# URN: test:coach-ops:worker-grid-dashboard:M002-UNIT-001-cards-built-from-runtime
# Acceptance: acc:coach-ops:M002-UNIT-001-cards-built-from-runtime
# WMBT: wmbt:coach-ops:M002
# Phase: GREEN
# Layer: domain
"""build_cards maps reader output → renderable worker cards (pure transform)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from atdd.coach.runtime.dashboard import Worker, build_cards, render_card
from atdd.coach.runtime.reader import AgentState

NOW = datetime(2026, 6, 10, 20, 0, 0, tzinfo=timezone.utc)


def _agent(agent_id, issue, phase=None, heartbeat_age_s=10):
    return AgentState(
        agent_id=agent_id,
        issue=issue,
        phase=phase,
        last_heartbeat=NOW - timedelta(seconds=heartbeat_age_s),
        status="running",
    )


def test_one_card_per_agent_not_per_issue():
    agents = [_agent("a·1036·coder", 1036), _agent("b·1036·tester", 1036)]
    cards = build_cards(agent_states=agents, issue_phases={}, now=NOW)
    assert len(cards) == 2
    assert {c.role for c in cards} == {"coder", "tester"}
    assert all(c.issue == 1036 for c in cards)


def test_phase_falls_back_to_issue_phases_when_agent_phase_missing():
    cards = build_cards(
        agent_states=[_agent("x·1050·planner", 1050, phase=None)],
        issue_phases={1050: "PLANNED"},
        now=NOW,
    )
    assert cards[0].phase == "PLANNED"


def test_cards_ordered_by_lifecycle_phase():
    ws = [
        Worker(issue=1, role="coder", phase="REFACTOR"),
        Worker(issue=2, role="planner", phase="INIT"),
        Worker(issue=3, role="tester", phase="GREEN"),
    ]
    cards = build_cards(agent_states=ws, issue_phases={}, now=NOW)
    assert [c.phase for c in cards] == ["INIT", "GREEN", "REFACTOR"]


def test_state_is_live_or_stopped_from_surface():
    # Surface known-closed → stopped; surface open → live. No idle/paused.
    stopped = Worker(issue=1, role="coder", surface="surface:9", phase="REFACTOR",
                     started_at=NOW - timedelta(hours=1))
    live = Worker(issue=2, role="coder", surface="surface:1", phase="GREEN",
                  started_at=NOW - timedelta(minutes=20))
    cards = build_cards(agent_states=[stopped, live], issue_phases={},
                        live_surfaces={"surface:1"}, now=NOW)
    by = {c.issue: c.state for c in cards}
    assert by[1] == "stopped" and by[2] == "live"


def test_live_card_shows_started_and_state():
    w = Worker(issue=1, role="coder", surface="surface:9", phase="GREEN",
               started_at=NOW - timedelta(minutes=5))
    card = build_cards(agent_states=[w], issue_phases={}, live_surfaces={"surface:9"}, now=NOW)[0]
    assert card.state == "live"
    rendered = "\n".join(render_card(card, width=44))
    assert "started" in rendered and "live" in rendered and "up " not in rendered


def test_stopped_card_shows_state_not_growing_counter():
    w = Worker(issue=1, role="coder", surface="surface:9", phase="REFACTOR",
               started_at=NOW - timedelta(days=2))
    card = build_cards(agent_states=[w], issue_phases={}, live_surfaces=set(), now=NOW)[0]
    assert card.state == "stopped"
    rendered = "\n".join(render_card(card, width=44))
    assert "stopped" in rendered and "ago" not in rendered


def test_channel_events_feed_and_last_from_escalations():
    # Per-worker escalations become the card's events; last = newest event time.
    w = Worker(
        issue=1, role="coder", surface="surface:9", phase="RED",
        started_at=NOW - timedelta(hours=1),
        escalations=[
            {"ts": NOW - timedelta(minutes=40), "severity": "block", "reason": "worker idle — hard-blocked"},
            {"ts": NOW - timedelta(minutes=5), "severity": "warn", "reason": "slow output"},
        ],
    )
    card = build_cards(agent_states=[w], issue_phases={}, live_surfaces={"surface:9"}, now=NOW)[0]
    assert len(card.events) == 2
    assert card.events[0].text == "slow output"  # newest first
    assert card.last == card.events[0].time
    rendered = "\n".join(render_card(card, width=50))
    assert "channel" in rendered and "hard-blocked" in rendered and "slow output" in rendered


def test_clock_is_absolute_hhmm_today_and_dated_when_older():
    import re

    from atdd.coach.runtime.dashboard import _fmt_clock

    today = _fmt_clock(NOW - timedelta(minutes=5), NOW)
    older = _fmt_clock(NOW - timedelta(days=3), NOW)
    assert re.fullmatch(r"\d{2}:\d{2}", today)
    assert re.search(r"[A-Za-z]{3} \d+ \d{2}:\d{2}", older)


def test_duration_formats_long_spans_as_days():
    from atdd.coach.runtime.dashboard import _fmt_secs

    assert _fmt_secs(22 * 86400 + 9 * 3600 + 26 * 60) == "22d09h"
    assert _fmt_secs(90 * 60) == "1h30m"
    assert _fmt_secs(45) == "0m45s"
