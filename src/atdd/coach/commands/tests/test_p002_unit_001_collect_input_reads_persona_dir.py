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

The persona-id derivation is asserted directly: a co-spawned observer
(`-observer` suffix) watches the persona dir; a bare id is the documented
L1 self-watch fallback. (The original second test asserted a hard
ValueError on a bare id; that was retargeted under #713 GREEN with user
authorization because ``Observer`` is dual-use — the co-spawned observer
AND the L1 generic per-agent watcher — so a bare id is a valid mode, not
an error.)
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


def test_persona_dir_is_derived_from_the_observer_suffix(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"

    # A co-spawned observer's id ends with `-observer`; the persona id is
    # that id minus the suffix and the persona dir it watches is NOT the
    # observer's own dir.
    obs = observer.Observer(
        agent_id="planner-713-abc-observer",
        runtime_dir=runtime,
        rules_dir=None,
    )
    assert obs.persona_agent_id == "planner-713-abc"
    assert obs.persona_dir.name == "planner-713-abc"
    assert obs.persona_dir != obs.agent_dir, (
        "a co-spawned observer must watch the persona dir, not its own"
    )

    # A bare id is the documented L1 self-watch fallback — it watches that
    # agent directly and never silently claims a different persona.
    legacy = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=None,
    )
    assert legacy.persona_agent_id == "agent-A"
