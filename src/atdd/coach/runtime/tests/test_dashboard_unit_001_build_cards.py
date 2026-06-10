# URN: test:coach-ops:coach-dashboard:PLACEHOLDER-UNIT-001-build-cards
# WMBT: wmbt:coach-ops:PLACEHOLDER   # FIXME(transplant): set real WMBT id once the atdd issue exists
# Phase: RED
# Layer: domain
"""build_cards maps reader output → renderable worker cards (pure transform)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from atdd.coach.runtime.dashboard import STALL_AFTER_SECONDS, Worker, build_cards
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


def test_stalled_flag_set_past_threshold_and_sorted_first():
    fresh = _agent("fresh·1000·coder", 1000, heartbeat_age_s=30)
    stale = _agent("stale·1030·planner", 1030, heartbeat_age_s=STALL_AFTER_SECONDS + 60)
    cards = build_cards(agent_states=[fresh, stale], issue_phases={}, now=NOW)
    assert cards[0].issue == 1030 and cards[0].stalled is True
    assert cards[1].issue == 1000 and cards[1].stalled is False


def test_elapsed_is_human_readable():
    cards = build_cards(
        agent_states=[_agent("x·1·coder", 1, heartbeat_age_s=12 * 60 + 4)],
        issue_phases={},
        now=NOW,
    )
    assert cards[0].elapsed == "12m04s"


def test_elapsed_measures_runtime_from_spawn_not_last_activity():
    # A Worker spawned 1h ago whose last heartbeat was 30s ago: elapsed is the
    # full runtime since spawn, while stall is judged from the recent heartbeat.
    w = Worker(
        issue=1036,
        role="coder",
        started_at=NOW - timedelta(hours=1, minutes=5),
        last_heartbeat=NOW - timedelta(seconds=30),
        phase="GREEN",
    )
    card = build_cards(agent_states=[w], issue_phases={}, now=NOW)[0]
    assert card.elapsed == "1h05m"
    assert card.stalled is False
    assert card.role == "coder" and card.phase == "GREEN"
