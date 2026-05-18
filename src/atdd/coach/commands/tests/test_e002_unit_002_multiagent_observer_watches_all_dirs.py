# URN: test:observe-and-correct:observer-runtime-and-rules:E002-UNIT-002-multiagent-observer-watches-all-dirs
# Acceptance: acc:observe-and-correct:E002-UNIT-002-multiagent-observer-watches-all-dirs
# WMBT: wmbt:observe-and-correct:E002
# Phase: RED
# Layer: unit
# Runtime: python
# Assertion: behavioral
"""E002-UNIT-002 — MultiAgentObserver discovers and scans all agent dirs
under runtime_root/agents/* in a single loop iteration.

RED: MultiAgentObserver does not exist yet.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_multiagent_observer_watches_all_dirs(tmp_path):
    """MultiAgentObserver._loop_once() calls scan_once for each agent dir."""
    from atdd.coach.commands.observer import MultiAgentObserver

    # Set up 3 agent dirs
    agents_dir = tmp_path / "agents"
    for name in ("agent-A", "agent-B", "agent-C"):
        d = agents_dir / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "output.log").write_text("hello\n")

    scanned: list[str] = []

    obs = MultiAgentObserver(runtime_root=tmp_path)

    # Patch Observer.scan_once to record calls instead of actually scanning
    import atdd.coach.commands.observer as obs_mod
    original_observer_cls = obs_mod.Observer

    class _RecordingObserver(original_observer_cls):
        def scan_once(self) -> None:
            scanned.append(self.agent_id)

    obs_mod.Observer = _RecordingObserver
    try:
        obs._loop_once()
    finally:
        obs_mod.Observer = original_observer_cls

    assert set(scanned) == {"agent-A", "agent-B", "agent-C"}, (
        f"Expected all 3 agent dirs scanned, got {scanned}"
    )
    assert len(scanned) == 3, (
        f"Expected exactly 3 scan_once calls (no duplicates), got {len(scanned)}"
    )
