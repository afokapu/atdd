# URN: test:integration-hardening:L001-INTEGRATION-001-observer-alongside-agent
# Acceptance: acc:integration-hardening:L001-INTEGRATION-001-observer-alongside-agent
# WMBT: wmbt:integration-hardening:L001
# Phase: GREEN
# Layer: integration
"""L001-INTEGRATION-001 — observer co-spawned alongside phase agent.

Per spec §8.3: every spawned phase agent has a co-spawned observer whose
pid is recorded in `.atdd/runtime/agents/<id>/observer_pid.json`.
Correction events appear in events.jsonl when a rule predicate fires.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _write_agent_manifest(agents_dir: Path, agent_id: str, issue: int, persona: str = "coder") -> Path:
    agent_dir = agents_dir / agent_id
    agent_dir.mkdir(parents=True)
    manifest = {
        "persona": persona,
        "agent_id": agent_id,
        "issue": issue,
    }
    (agent_dir / "manifest.json").write_text(json.dumps(manifest))
    return agent_dir


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    return tmp_path / ".atdd" / "runtime"


@pytest.fixture()
def ctx_for(runtime_root):
    from atdd.coach.handlers.state_machine import CoachContext

    def _make(issue_number: int = 589, dry_run: bool = False):
        return CoachContext(issue_number=issue_number, dry_run=dry_run)

    return _make


class TestObserverAlongsideAgent:
    """observer_pid.json is written when a phase agent manifest exists."""

    def test_observer_pid_recorded_after_handle(
        self,
        runtime_root: Path,
        ctx_for,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))
        agent_id = "coder-589-abc123"
        agent_dir = _write_agent_manifest(
            runtime_root / "agents", agent_id, 589
        )

        # Prevent real thread from starting.
        monkeypatch.setattr(
            "atdd.coach.commands.observer.Observer.start",
            lambda self: None,
        )

        from atdd.coach.handlers import observer as obs_handler
        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = ctx_for(issue_number=589)
        transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)
        result = obs_handler.handle(ctx, transition)

        assert result == HandlerResult.HANDLED
        pid_file = agent_dir / "observer_pid.json"
        assert pid_file.exists(), "observer_pid.json must be written per L1-INTEGRATION-001"
        data = json.loads(pid_file.read_text())
        assert data["agent_id"] == agent_id
        assert data["phase"] == "PLANNED"

    def test_reviewer_agent_excluded_from_observer_target(
        self,
        runtime_root: Path,
        ctx_for,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Observer must not attach to reviewer agents — only to phase agents."""
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))
        _write_agent_manifest(runtime_root / "agents", "reviewer-589-x", 589, persona="reviewer")

        monkeypatch.setattr(
            "atdd.coach.commands.observer.Observer.start",
            lambda self: None,
        )

        from atdd.coach.handlers import observer as obs_handler
        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = ctx_for(issue_number=589)
        transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)
        result = obs_handler.handle(ctx, transition)

        # No non-reviewer agent exists → NOOP, not HANDLED
        assert result == HandlerResult.NOOP

    def test_dry_run_returns_noop(
        self,
        runtime_root: Path,
        ctx_for,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))
        _write_agent_manifest(runtime_root / "agents", "coder-589-dry", 589)

        from atdd.coach.handlers import observer as obs_handler
        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = ctx_for(issue_number=589, dry_run=True)
        transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)
        result = obs_handler.handle(ctx, transition)

        assert result == HandlerResult.NOOP

    def test_no_agent_manifest_returns_noop(
        self,
        runtime_root: Path,
        ctx_for,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))
        (runtime_root / "agents").mkdir(parents=True)

        from atdd.coach.handlers import observer as obs_handler
        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = ctx_for(issue_number=589)
        transition = Transition(src=Phase.INIT, dst=Phase.PLANNED)
        result = obs_handler.handle(ctx, transition)

        assert result == HandlerResult.NOOP

    def test_most_recent_agent_selected_when_multiple_exist(
        self,
        runtime_root: Path,
        ctx_for,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """When multiple phase agents exist, observer attaches to the most recent one."""
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))
        import time

        agents_dir = runtime_root / "agents"
        _write_agent_manifest(agents_dir, "coder-589-old", 589)
        time.sleep(0.01)
        _write_agent_manifest(agents_dir, "coder-589-new", 589)

        monkeypatch.setattr(
            "atdd.coach.commands.observer.Observer.start",
            lambda self: None,
        )

        from atdd.coach.handlers import observer as obs_handler
        from atdd.coach.handlers.state_machine import HandlerResult, Phase, Transition

        ctx = ctx_for(issue_number=589)
        transition = Transition(src=Phase.RED, dst=Phase.GREEN)
        result = obs_handler.handle(ctx, transition)

        assert result == HandlerResult.HANDLED
        # observer_pid.json should be in the newer agent's dir
        pid_file = agents_dir / "coder-589-new" / "observer_pid.json"
        assert pid_file.exists()
