# URN: test:observe-and-correct:observer-runtime-and-rules:P002-UNIT-002-time-token-fields-populated
# Acceptance: acc:observe-and-correct:P002-UNIT-002-time-token-fields-populated
# WMBT: wmbt:observe-and-correct:P002
# Phase: RED
# Layer: application
"""P002-UNIT-002 — collect_input must populate now/last_token_at/heartbeat_mtime.

Issue #713 Layer 2: ``collect_input`` builds ``ObservedInput`` with
``now`` / ``last_token_at`` / ``heartbeat_mtime`` left at their ``None``
defaults. The token-silence (02) and missed-heartbeat (05) predicates
short-circuit to no-fire when those are ``None`` — so the rules are
structurally dead.

RED: these tests fail today because collect_input never sets the fields.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def test_collect_input_populates_now_last_token_and_heartbeat(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    persona_dir = runtime / "agents" / "coder-713-xyz"
    persona_dir.mkdir(parents=True)
    (persona_dir / "output.log").write_text("some token output\n")
    (persona_dir / "heartbeat.json").write_text(
        json.dumps({"ts": "2026-05-15T00:00:00Z"})
    )

    obs = observer.Observer(
        agent_id="coder-713-xyz-observer",
        runtime_dir=runtime,
        rules_dir=None,
    )
    ci = obs.collect_input()

    assert ci.now is not None, "collect_input must set ObservedInput.now"
    assert ci.last_token_at is not None, (
        "collect_input must set last_token_at from persona output activity"
    )
    assert ci.heartbeat_mtime is not None, (
        "collect_input must set heartbeat_mtime from the persona heartbeat.json"
    )


def test_populated_fields_let_token_silence_rule_fire(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    persona_dir = runtime / "agents" / "coder-713-xyz"
    persona_dir.mkdir(parents=True)
    log = persona_dir / "output.log"
    log.write_text("earlier work\n")
    # The persona has been silent for ~2h — far past the 90s threshold.
    stale = time.time() - 7200
    os.utime(log, (stale, stale))

    obs = observer.Observer(
        agent_id="coder-713-xyz-observer",
        runtime_dir=runtime,
        rules_dir=None,
    )
    ci = obs.collect_input()

    predicate = observer._make_token_silence_predicate(90)
    assert predicate(ci), (
        "with now/last_token_at populated and a >90s gap, the token-silence "
        "predicate must fire instead of short-circuiting on None"
    )
