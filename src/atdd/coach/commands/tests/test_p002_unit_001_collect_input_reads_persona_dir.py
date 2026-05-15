# URN: test:observe-and-correct:observer-runtime-and-rules:P002-UNIT-001-collect-input-reads-persona-dir
# Acceptance: acc:observe-and-correct:P002-UNIT-001-collect-input-reads-persona-dir
# WMBT: wmbt:observe-and-correct:P002
# Phase: RED
# Layer: application
"""P002-UNIT-001 — collect_input must read the *persona's* runtime dir.

Issue #713 Layer 1: ``Observer.collect_input`` -> ``_tail_output_log``
reads ``self.agent_dir`` which is built from the observer's OWN agent_id
(``planner-NNN-xxx-observer``). The observer therefore watches itself.

The persona agent_id is the observer agent_id with the ``-observer``
suffix stripped; collect_input must read ``runtime/agents/<persona-id>/``.

RED: these tests fail today because collect_input reads the observer's
own dir and the constructor does not validate the ``-observer`` suffix.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_collect_input_reads_the_persona_output_log(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    persona_dir = runtime / "agents" / "planner-713-abc"
    observer_dir = runtime / "agents" / "planner-713-abc-observer"
    persona_dir.mkdir(parents=True)
    observer_dir.mkdir(parents=True)
    (persona_dir / "output.log").write_text("PERSONA-TOKENS the agent said this\n")
    (observer_dir / "output.log").write_text("OBSERVER-OWN noise the observer emitted\n")

    obs = observer.Observer(
        agent_id="planner-713-abc-observer",
        runtime_dir=runtime,
        rules_dir=None,
    )
    collected = obs.collect_input()
    joined = "\n".join(collected.log_lines)

    assert "PERSONA-TOKENS" in joined, (
        "collect_input must read the persona's output.log "
        "(runtime/agents/planner-713-abc/), not the observer's own dir"
    )
    assert "OBSERVER-OWN" not in joined, (
        "collect_input must NOT read the observer's own output.log"
    )


def test_observer_agent_id_without_suffix_is_rejected(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    # An observer agent_id MUST end with `-observer` so the persona id is
    # derivable. A bare id is ambiguous and must be rejected rather than
    # silently making the observer read its own dir.
    with pytest.raises(ValueError):
        observer.Observer(
            agent_id="planner-713-abc",
            runtime_dir=runtime,
            rules_dir=None,
        )
