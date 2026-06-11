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


def test_paused_is_idle_based_not_uptime_based():
    # A worker running 3h but active 2m ago is LIVE; a short worker idle 15m is
    # PAUSED. Liveness keys off recent activity, not total uptime.
    active = Worker(issue=1000, role="coder", phase="GREEN", surface="surface:1",
                    started_at=NOW - timedelta(hours=3), last_heartbeat=NOW - timedelta(minutes=2))
    quiet = Worker(issue=1030, role="coder", phase="GREEN", surface="surface:2",
                   started_at=NOW - timedelta(minutes=30), last_heartbeat=NOW - timedelta(minutes=15))
    by = {c.issue: c.state for c in build_cards(
        agent_states=[active, quiet], issue_phases={},
        live_surfaces={"surface:1", "surface:2"}, now=NOW)}
    assert by[1000] == "live"
    assert by[1030] == "paused"


def test_cards_ordered_by_lifecycle_phase():
    ws = [
        Worker(issue=1, role="coder", phase="REFACTOR", last_heartbeat=NOW),
        Worker(issue=2, role="planner", phase="INIT", last_heartbeat=NOW),
        Worker(issue=3, role="tester", phase="GREEN", last_heartbeat=NOW),
    ]
    cards = build_cards(agent_states=ws, issue_phases={}, now=NOW)
    assert [c.phase for c in cards] == ["INIT", "GREEN", "REFACTOR"]


def test_duration_is_human_readable():
    # Live worker → uptime = now − spawn, humanized.
    w = Worker(issue=1, role="coder", surface="surface:1",
               started_at=NOW - timedelta(minutes=12, seconds=4), last_heartbeat=NOW)
    card = build_cards(agent_states=[w], issue_phases={}, live_surfaces={"surface:1"}, now=NOW)[0]
    assert card.duration == "12m04s"  # last − spawn span


def test_stopped_duration_is_last_activity_minus_spawn():
    # A STOPPED worker shows run duration (last − spawn ≈ 1h04m), not now − spawn.
    w = Worker(
        issue=1036,
        role="coder",
        surface="surface:9",
        started_at=NOW - timedelta(hours=1, minutes=5),
        last_heartbeat=NOW - timedelta(seconds=30),
        phase="GREEN",
    )
    card = build_cards(agent_states=[w], issue_phases={}, live_surfaces=set(), now=NOW)[0]
    assert card.state == "stopped"
    assert card.duration == "1h04m"
    assert card.role == "coder" and card.phase == "GREEN"


def test_worker_state_is_live_paused_or_stopped():
    # Surface known-closed → stopped (regardless of idle).
    stopped = Worker(issue=1, role="coder", surface="surface:9", phase="REFACTOR",
                     started_at=NOW - timedelta(hours=1), last_heartbeat=NOW - timedelta(minutes=30))
    # Surface open, idle < 10m → live.
    live = Worker(issue=2, role="coder", surface="surface:1", phase="GREEN",
                  started_at=NOW - timedelta(minutes=20), last_heartbeat=NOW - timedelta(minutes=2))
    # Surface open, idle ≥ 10m → paused.
    paused = Worker(issue=3, role="coder", surface="surface:2", phase="RED",
                    started_at=NOW - timedelta(hours=1), last_heartbeat=NOW - timedelta(minutes=15))
    cards = build_cards(agent_states=[stopped, live, paused], issue_phases={},
                        live_surfaces={"surface:1", "surface:2"}, now=NOW)
    by = {c.issue: c.state for c in cards}
    assert by[1] == "stopped" and by[2] == "live" and by[3] == "paused"


def test_finished_worker_shows_ran_and_ended_not_uptime():
    # Surface NOT in the live set → finished → 'ran <dur> · ended <ago>', no 'up'.
    w = Worker(
        issue=1, role="coder", surface="surface:9",
        started_at=NOW - timedelta(days=2),
        last_heartbeat=NOW - timedelta(days=2) + timedelta(minutes=30),
        phase="REFACTOR",
    )
    card = build_cards(agent_states=[w], issue_phases={}, live_surfaces=set(), now=NOW)[0]
    assert card.state == "stopped"
    rendered = "\n".join(render_card(card, width=44))
    assert "ran 30m" in rendered and "ended" in rendered
    assert "up " not in rendered and "ago" not in rendered


def test_live_worker_shows_uptime():
    w = Worker(
        issue=1, role="coder", surface="surface:9",
        started_at=NOW - timedelta(minutes=5),
        last_heartbeat=NOW - timedelta(seconds=10),
        phase="GREEN",
    )
    card = build_cards(
        agent_states=[w], issue_phases={}, live_surfaces={"surface:9"}, now=NOW
    )[0]
    assert card.state == "live"
    rendered = "\n".join(render_card(card, width=44))
    assert "started" in rendered and "last" in rendered and "up " not in rendered


def test_stopped_elapsed_is_bounded_for_an_old_worker():
    # Spawned 2 days ago, last activity 30m after spawn → ran 30m, NOT 48h.
    w = Worker(
        issue=5,
        role="coder",
        surface="surface:9",
        started_at=NOW - timedelta(days=2),
        last_heartbeat=NOW - timedelta(days=2) + timedelta(minutes=30),
        phase="REFACTOR",
    )
    card = build_cards(agent_states=[w], issue_phases={}, live_surfaces=set(), now=NOW)[0]
    assert card.state == "stopped" and card.duration == "30m00s"


def test_clock_is_absolute_hhmm_today_and_dated_when_older():
    import re

    from atdd.coach.runtime.dashboard import _fmt_clock

    today = _fmt_clock(NOW - timedelta(minutes=5), NOW)
    older = _fmt_clock(NOW - timedelta(days=3), NOW)
    assert re.fullmatch(r"\d{2}:\d{2}", today)          # HH:MM, no "ago"
    assert re.search(r"[A-Za-z]{3} \d+ \d{2}:\d{2}", older)  # e.g. "Jun 7 19:55"
