# URN: test:coach-ops:worker-grid-dashboard:M002-UNIT-001-cards-built-from-runtime
# Acceptance: acc:coach-ops:M002-UNIT-001-cards-built-from-runtime
# WMBT: wmbt:coach-ops:M002
# Phase: GREEN
# Layer: domain
"""build_cards maps reader output → renderable worker cards (pure transform)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from atdd.coach.runtime.dashboard import STALL_AFTER_SECONDS, Worker, build_cards, render_card
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


def test_stalled_when_live_and_running_past_threshold():
    short = Worker(issue=1000, role="coder", phase="GREEN",
                   started_at=NOW - timedelta(minutes=30), last_heartbeat=NOW)
    longrun = Worker(issue=1030, role="coder", phase="GREEN",
                     started_at=NOW - timedelta(seconds=STALL_AFTER_SECONDS + 60),
                     last_heartbeat=NOW)
    by = {c.issue: c for c in build_cards(agent_states=[short, longrun], issue_phases={}, now=NOW)}
    assert by[1030].stalled is True   # live, running > 2h
    assert by[1000].stalled is False  # live, 30m


def test_finished_long_runner_is_not_stalled():
    # Surface closed → not live → never stalled, however long it ran.
    w = Worker(issue=5, role="coder", surface="surface:9", phase="REFACTOR",
               started_at=NOW - timedelta(hours=5), last_heartbeat=NOW - timedelta(hours=4))
    card = build_cards(agent_states=[w], issue_phases={}, live_surfaces=set(), now=NOW)[0]
    assert card.live is False and card.stalled is False


def test_cards_ordered_by_lifecycle_phase():
    ws = [
        Worker(issue=1, role="coder", phase="REFACTOR", last_heartbeat=NOW),
        Worker(issue=2, role="planner", phase="INIT", last_heartbeat=NOW),
        Worker(issue=3, role="tester", phase="GREEN", last_heartbeat=NOW),
    ]
    cards = build_cards(agent_states=ws, issue_phases={}, now=NOW)
    assert [c.phase for c in cards] == ["INIT", "GREEN", "REFACTOR"]


def test_elapsed_is_human_readable():
    cards = build_cards(
        agent_states=[_agent("x·1·coder", 1, heartbeat_age_s=12 * 60 + 4)],
        issue_phases={},
        now=NOW,
    )
    assert cards[0].elapsed == "12m04s"


def test_elapsed_is_run_duration_last_activity_minus_spawn():
    # Spawned 1h5m ago, last heartbeat 30s ago → duration = last − spawn ≈ 1h04m
    # (NOT now − spawn), while stall is judged from the recent heartbeat.
    w = Worker(
        issue=1036,
        role="coder",
        started_at=NOW - timedelta(hours=1, minutes=5),
        last_heartbeat=NOW - timedelta(seconds=30),
        phase="GREEN",
    )
    card = build_cards(agent_states=[w], issue_phases={}, now=NOW)[0]
    assert card.elapsed == "1h04m"
    assert card.stalled is False
    assert card.role == "coder" and card.phase == "GREEN"


def test_finished_worker_shows_ran_and_ended_not_uptime():
    # Surface NOT in the live set → finished → 'ran <dur> · ended <ago>', no 'up'.
    w = Worker(
        issue=1, role="coder", surface="surface:9",
        started_at=NOW - timedelta(days=2),
        last_heartbeat=NOW - timedelta(days=2) + timedelta(minutes=30),
        phase="REFACTOR",
    )
    card = build_cards(agent_states=[w], issue_phases={}, live_surfaces=set(), now=NOW)[0]
    assert card.live is False
    rendered = "\n".join(render_card(card, width=44))
    assert "ran 30m" in rendered and "ended" in rendered and "ago" in rendered
    assert "up " not in rendered


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
    assert card.live is True
    assert "up" in "\n".join(render_card(card, width=44))


def test_elapsed_is_bounded_for_an_old_finished_worker():
    # Spawned 2 days ago, last activity 30m after spawn → ran 30m, NOT 48h.
    w = Worker(
        issue=5,
        role="coder",
        started_at=NOW - timedelta(days=2),
        last_heartbeat=NOW - timedelta(days=2) + timedelta(minutes=30),
        phase="REFACTOR",
    )
    card = build_cards(agent_states=[w], issue_phases={}, now=NOW)[0]
    assert card.elapsed == "30m00s"
