# URN: test:observe-and-correct:observer-runtime-and-rules:P002-SMOKE-002-acquisition-and-observability
# Acceptance: acc:observe-and-correct:P002-UNIT-003-persona-output-stream-acquired
# Acceptance: acc:observe-and-correct:P002-INTEGRATION-001-persona-heartbeat-produced
# Acceptance: acc:observe-and-correct:P002-UNIT-004-observer-status-line-and-trace
# Acceptance: acc:observe-and-correct:P002-UNIT-005-universal-operator-visibility
# WMBT: wmbt:observe-and-correct:P002
# Phase: SMOKE
# Layer: backend.integration
"""P002-SMOKE-002 — observer input acquisition + observability against REAL infra.

Smoke coverage for the #713 acquisition and observability layers, with
no mocks of observer internals:

- surface acquisition (Layer 3): a REAL subprocess emits agent output to
  a REAL surface; the observer's ``surface_capture`` reads it, acquires
  it into the persona's real ``output.log``, and a REAL rule loaded from
  a real rule YAML on disk fires and persists a real correction.
- heartbeat producer (scope item 2): the REAL ``start_heartbeat_ticker``
  thread refreshes ``heartbeat.json`` over real wall-clock intervals and
  the observer's real ``collect_input`` reads a fresh ``heartbeat_mtime``.
- observability (Layer 4): the REAL ``atdd observer`` CLI is spawned as a
  subprocess for every observer-bearing persona type and the operator
  status line + ingest trace appears on real stdout.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


# src/atdd/coach/commands/tests/ -> parents[4] = src ; parents[5] = repo root
SRC_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT = Path(__file__).resolve().parents[5]
REAL_RULE_01 = REPO_ROOT / ".atdd" / "observer" / "rules" / "01-unstructured-question.yaml"


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{SRC_ROOT}{os.pathsep}{existing}" if existing else str(SRC_ROOT)
    )
    return env


def test_surface_capture_acquires_real_process_output_and_fires_real_rule(
    tmp_path: Path,
):
    """Layer 3 — real subprocess output, real surface, real rule on disk."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    persona_dir = runtime / "agents" / "coder-713-surface"
    persona_dir.mkdir(parents=True)

    # A REAL persona process emits a free-form question to its surface.
    surface_file = tmp_path / "persona-surface.txt"
    subprocess.run(
        [
            "python3",
            "-c",
            "import sys; "
            "open(sys.argv[1], 'w').write("
            "'agent output: Should I use approach A or approach B?\\n')",
            str(surface_file),
        ],
        check=True,
    )

    def real_surface_capture() -> str:
        """Capture the persona's live surface — a real read of real state."""
        return surface_file.read_text(encoding="utf-8")

    # A REAL rule, copied from the repo's co-spawn rule registry on disk.
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    shutil.copy(REAL_RULE_01, rules_dir / REAL_RULE_01.name)

    obs = observer.Observer(
        agent_id="coder-713-surface-observer",
        runtime_dir=runtime,
        rules_dir=rules_dir,
        surface_capture=real_surface_capture,
    )
    obs.load_rules()
    corrections = obs.scan_once()

    # The acquired surface delta is persisted to the real persona output.log.
    persisted = (persona_dir / "output.log").read_text(encoding="utf-8")
    assert "approach A or approach B" in persisted

    # The real log-regex rule fired on the acquired persona output.
    rule_ids = [c.rule_id for c in corrections]
    assert "coach.observer.unstructured-question" in rule_ids, (
        f"the real rule 01 must fire on the acquired persona output; "
        f"got {rule_ids}"
    )

    cor_path = runtime / "agents" / "coder-713-surface-observer" / "corrections.jsonl"
    assert cor_path.exists(), "the observer must persist a real corrections.jsonl"


def test_heartbeat_ticker_feeds_real_observer_liveness(tmp_path: Path):
    """Heartbeat producer — real ticker thread, real wall-clock intervals."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    persona_dir = runtime / "agents" / "planner-713-hb"
    persona_dir.mkdir(parents=True)

    ticker = observer.start_heartbeat_ticker(agent_dir=persona_dir, interval=0.2)
    try:
        hb = persona_dir / "heartbeat.json"
        deadline = time.time() + 5.0
        while not hb.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert hb.exists(), "the real heartbeat ticker must write heartbeat.json"

        first_mtime = hb.stat().st_mtime
        time.sleep(0.6)
        assert hb.stat().st_mtime > first_mtime, (
            "heartbeat.json mtime must advance on real wall-clock intervals"
        )

        # The real observer reads the real heartbeat the ticker produced.
        obs = observer.Observer(
            agent_id="planner-713-hb-observer",
            runtime_dir=runtime,
            rules_dir=None,
        )
        ci = obs.collect_input()
        assert ci.heartbeat_mtime is not None, (
            "collect_input must read the heartbeat_mtime the ticker produced"
        )
        # Heartbeat is fresh -> rule 05 (300s threshold) must NOT fire.
        stale_predicate = observer._make_heartbeat_stale_predicate(300)
        assert not stale_predicate(ci), (
            "a freshly-ticked heartbeat must not be flagged stale"
        )
    finally:
        ticker.stop()


# Every observer-bearing entry point — same set as the universal-visibility
# unit test, exercised here through the real CLI process.
PERSONA_ENTRY_POINTS = ["planner", "tester", "coder", "reviewer", "coach-monitor"]


@pytest.mark.parametrize("persona", PERSONA_ENTRY_POINTS)
def test_observer_cli_renders_status_line_real_process(
    tmp_path: Path, persona: str
):
    """Layer 4 — the real `atdd observer` CLI renders the operator status
    line for every observer-bearing persona type."""
    runtime = tmp_path / persona / ".atdd" / "runtime"
    rules_dir = tmp_path / persona / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    persona_id = f"{persona}-713-cli"
    persona_dir = runtime / "agents" / persona_id
    persona_dir.mkdir(parents=True)
    (persona_dir / "output.log").write_text(
        f"{persona} persona is doing real work\n", encoding="utf-8"
    )

    r = subprocess.run(
        [
            "python3", "-m", "atdd", "observer", "run",
            "--agent-id", f"{persona_id}-observer",
            "--runtime-dir", str(runtime),
            "--rules-dir", str(rules_dir),
            "--once",
        ],
        env=_cli_env(),
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"observer run failed: stderr={r.stderr}"

    out = r.stdout
    assert persona_id in out, (
        f"the real observer CLI must name the watched persona for '{persona}'"
    )
    assert "rules loaded" in out and "last scan" in out and "corrections" in out, (
        f"the real observer CLI must render the operator status line; got: {out!r}"
    )
    assert "persona is doing real work" in out, (
        "the operator must see what the observer ingested this scan"
    )
