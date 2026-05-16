# URN: test:observe-and-correct:observer-runtime-and-rules:P002-UNIT-003-persona-output-stream-acquired
# Acceptance: acc:observe-and-correct:P002-UNIT-003-persona-output-stream-acquired
# WMBT: wmbt:observe-and-correct:P002
# Phase: RED
# Layer: application
"""P002-UNIT-003 — the persona's output stream must be acquired.

Issue #713 Layer 3: nothing produces the persona's ``output.log``. The
planner decision (P002.yaml) is option (a): the co-spawned observer
captures the persona's multiplexer surface and tails the delta into the
persona's ``output.log`` — so the log-regex rules receive real agent
output.

The injection seam under test is a ``surface_capture`` callable passed
to ``Observer`` (stands in for ``cmux capture-pane``).

RED: this test fails today — ``Observer`` does not accept a
``surface_capture`` argument and never acquires the persona stream.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_persona_surface_output_is_acquired_into_log_lines(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    persona_dir = runtime / "agents" / "tester-713-q"
    persona_dir.mkdir(parents=True)

    surface_text = "agent output: Should I use approach A or approach B?\n"

    def fake_surface_capture() -> str:
        """Stand-in for `cmux capture-pane` against the persona surface."""
        return surface_text

    obs = observer.Observer(
        agent_id="tester-713-q-observer",
        runtime_dir=runtime,
        rules_dir=None,
        surface_capture=fake_surface_capture,
    )
    ci = obs.collect_input()
    joined = "\n".join(ci.log_lines)

    assert "approach A or approach B" in joined, (
        "the observer must acquire the persona surface output into "
        "ObservedInput.log_lines so log-regex rules see real agent output"
    )

    persisted = (persona_dir / "output.log").read_text()
    assert "approach A or approach B" in persisted, (
        "the acquired surface delta must be tailed into the persona's "
        "output.log as a durable artifact"
    )
