# URN: test:mediate-worker-decisions:bridge-cmux-feed:E011-UNIT-001-decider-carries-coach-convention
# Acceptance: acc:mediate-worker-decisions:E011-UNIT-001-decider-carries-coach-convention
# WMBT: wmbt:mediate-worker-decisions:E011
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""E011-UNIT-001 — the decider's claude -p invocation carries the coach convention.

The autonomous decider (``LlmCoach`` over the real ``claude`` provider CLI) must
decide AS A COACH: the coach convention / operating protocol resolved from the
repo reaches the actual ``claude -p`` argv as an appended system prompt — not a
blank LLM call. We capture the argv the provider CLI hands to ``subprocess.run``
and assert it carries ``--append-system-prompt`` plus the convention text.
"""
from __future__ import annotations

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration import llm_coach
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.coach_context import (
    load_coach_context,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.llm_coach import (
    LlmCoach,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionPrompt,
    DecisionRequest,
    Option,
    WorkerRef,
)


def _single_request() -> DecisionRequest:
    return DecisionRequest(
        request_id="req-1",
        worker=WorkerRef(surface_id="s1", agent_handle_ref="req-1"),
        prompt=DecisionPrompt(
            raw_text="",
            question="shim vs tui-scrape fallback?",
            options=(Option("shim", "Use the shim"), Option("scrape", "Scrape the TUI")),
        ),
        source="cmux_feed",
        created_at="",
    )


def test_claude_argv_carries_the_coach_convention(monkeypatch):
    captured = {}

    class _FakeCompleted:
        stdout = "Use the shim"
        stderr = ""
        returncode = 0

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeCompleted()

    # capture the real provider CLI's subprocess argv (no claude is spawned)
    monkeypatch.setattr(llm_coach.subprocess, "run", _fake_run)

    # default provider = claude; the loader resolves the convention from the repo
    coach = LlmCoach(id_factory=lambda: "v1", ts_factory=lambda: "t")
    coach.mediate(_single_request())

    cmd = captured["cmd"]
    assert "claude" in cmd and "-p" in cmd
    assert "--append-system-prompt" in cmd, "the decider must decide as a coach"

    # the appended system prompt is the coach convention / operating protocol
    system_arg = cmd[cmd.index("--append-system-prompt") + 1]
    expected = load_coach_context()
    assert "Phase Machine Convention" in expected  # the loaded convention is real
    assert system_arg == expected
    assert "coach.phase-machine" in system_arg  # the operating-protocol text reached the argv
