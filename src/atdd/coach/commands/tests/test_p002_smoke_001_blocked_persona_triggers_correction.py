# URN: test:observe-and-correct:observer-runtime-and-rules:P002-SMOKE-001-blocked-persona-triggers-correction
# Acceptance: acc:observe-and-correct:P002-SMOKE-001-blocked-persona-triggers-correction
# WMBT: wmbt:observe-and-correct:P002
# Phase: SMOKE
# Layer: backend.integration
"""P002-SMOKE-001 — a blocked/silent persona must trigger a correction.

Issue #713 OBSINPUT-004: the lived #711 failure — a planner sat blocked
on a structured question for 12+ minutes and the observer's
token-silence rule never fired.

This smoke test exercises the real ``atdd observer`` CLI end-to-end
against a real runtime tree: a persona whose ``output.log`` has been
silent for ~2h, the real ``02-token-silence`` rule loaded from disk, and
``atdd observer run --once`` for the co-spawned observer. The observer
must derive the (stale) ``last_token_at`` from the persona dir and fire
rule 02, persisting a correction to ``corrections.jsonl``.

RED: fails today — collect_input reads the observer's own (empty) dir
and never populates ``last_token_at``, so rule 02 cannot fire.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


SRC_ROOT = Path(__file__).resolve().parents[4]

# Mirrors .atdd/observer/rules/02-token-silence.yaml (spec §8.3 row 02).
RULE_02_TOKEN_SILENCE = """\
rule_id: "coach.observer.token-silence"
trigger:
  type: token_silence
  threshold_seconds: 90
correction_text: |
  No tokens observed for {duration_seconds}s (threshold: 90s).
  If you are blocked, escalate via `atdd agent escalate`.
injection_method: cli-return
severity: 3
disposition: documentation-only
"""


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def test_silent_persona_triggers_token_silence_correction(tmp_path: Path):
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{SRC_ROOT}{os.pathsep}{existing}" if existing else str(SRC_ROOT)
    )

    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "02-token-silence.yaml").write_text(RULE_02_TOKEN_SILENCE)

    # The persona dir — what the observer must learn to read.
    persona_id = "planner-713-stall"
    persona_dir = runtime / "agents" / persona_id
    persona_dir.mkdir(parents=True)
    persona_log = persona_dir / "output.log"
    persona_log.write_text("Should I use approach A or B? (blocked, waiting)\n")
    # The persona has emitted no tokens for ~2h — well past the 90s threshold.
    stale = time.time() - 7200
    os.utime(persona_log, (stale, stale))

    observer_id = f"{persona_id}-observer"
    r = subprocess.run(
        [
            "python3", "-m", "atdd", "observer", "run",
            "--agent-id", observer_id,
            "--runtime-dir", str(runtime),
            "--rules-dir", str(rules_dir),
            "--once",
        ],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"observer run failed: stderr={r.stderr}"

    cor_path = runtime / "agents" / observer_id / "corrections.jsonl"
    assert cor_path.exists(), (
        "the observer must persist a correction for the stalled persona"
    )
    records = _read_jsonl(cor_path)
    assert any(
        rec.get("rule_id") == "coach.observer.token-silence"
        for rec in records
    ), (
        "rule 02 (token-silence) must fire for a persona silent past the "
        f"threshold — the lived #711 stall must not recur; got: {records}"
    )
