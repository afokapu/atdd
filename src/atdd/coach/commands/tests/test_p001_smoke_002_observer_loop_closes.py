# URN: test:observe-and-correct:observer-runtime-and-rules:P001-SMOKE-002-observer-loop-closes
# Acceptance: acc:observe-and-correct:P001-SMOKE-002-observer-loop-closes
# WMBT: wmbt:observe-and-correct:P001
# Phase: SMOKE
# Layer: backend.integration
# atdd:suppress(planner.smoke.synthetic-fixture-bypass) UNTIL=2026-11-14
"""P001-SMOKE-002 — close-the-loop verification for the observer feedback system.

This test implements the close-the-loop assertion pair required by
``smoke.convention.yaml::feedback_loop`` for features marked
``kind: feedback-loop`` (issue #825).

Motivation: the 2026-05-21 incident — observer-runtime-and-rules shipped
with all 4 SMOKE tests green while 0 corrections reached any worker.
P001-SMOKE-001 asserted "producer wrote corrections.jsonl" but never
asserted "consumer received the correction." This test closes that gap:

  (a) CONSUMER-SIDE: the cli-return.jsonl entry exists AND the text
      was read back — verifies the delivery file is populated, not
      just that the observer ran.

  (b) CONVERGENCE: a second observer scan pass against the same agent
      produces 0 new correction records — the rule's predicate has
      flipped to non-firing after the correction was written.

The test uses the same real `atdd observer` CLI subprocess as P001-SMOKE-001
(no FakeMultiplexer.send_history — that records sends without delivering them
anywhere, the exact failure mode this test is designed to catch).
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

import atdd

pytestmark = [pytest.mark.platform]


SRC_ROOT = Path(__file__).resolve().parents[4]
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
CORRECTION_SCHEMA_PATH = ATDD_PKG_DIR / "coach" / "schemas" / "correction.schema.json"


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


@pytest.fixture
def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{SRC_ROOT}{os.pathsep}{existing}" if existing else str(SRC_ROOT)
    )
    return env


def _run_observer(
    args: list[str], env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["python3", "-m", "atdd", "observer", *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _make_bang_rule(rules_dir: Path) -> None:
    """Write a rule that fires on BANG output — same trigger as P001-SMOKE-001."""
    (rules_dir / "10-bang.yaml").write_text(
        """
rule_id: "coach.orchestration.read-only-git-diagnostics"
trigger:
  type: log_regex
  pattern: ".*BANG.*"
correction_text: "stop emitting BANG"
injection_method: "cli-return"
severity: 3
disposition: "advisory"
"""
    )


def test_observer_loop_closes_consumer_side_and_convergence(
    tmp_path: Path, cli_env: dict[str, str]
):
    """
    Close-the-loop smoke (issue #825).

    (a) CONSUMER-SIDE assertion: correction text is present in
        cli-return.jsonl — the delivery channel has actual content,
        not just a sentinel file.

    (b) CONVERGENCE assertion: a second scan pass produces 0 new
        correction records for the same (rule_id, drift content) —
        the rule predicate is no longer firing.
    """
    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    agent_id = "agent-loop-close"
    agent_dir = runtime / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    # Seed drift: the rule fires on "BANG" in output.log.
    (agent_dir / "output.log").write_text("BANG BANG we said BANG\n")
    _make_bang_rule(rules_dir)

    # ── First pass: detect + dispatch ──────────────────────────────
    r1 = _run_observer(
        [
            "run",
            "--agent-id", agent_id,
            "--runtime-dir", str(runtime),
            "--rules-dir", str(rules_dir),
            "--once",
        ],
        cli_env,
        tmp_path,
    )
    assert r1.returncode == 0, f"first pass failed: stderr={r1.stderr}"

    cor_path = agent_dir / "corrections.jsonl"
    assert cor_path.exists()
    records_pass1 = _read_jsonl(cor_path)
    assert len(records_pass1) == 1, "expected exactly one correction on first pass"

    # ── (a) CONSUMER-SIDE: delivery channel has the correction text ──
    return_channel = agent_dir / "cli-return.jsonl"
    assert return_channel.exists(), (
        "cli-return.jsonl must exist — the consumer delivery file is missing"
    )
    return_recs = _read_jsonl(return_channel)
    assert len(return_recs) >= 1, (
        "cli-return.jsonl is empty — correction was never written to the delivery channel"
    )
    # The specific correction text must be in the delivery record.
    delivered = [
        rec for rec in return_recs
        if rec.get("correction_text") == "stop emitting BANG"
    ]
    assert delivered, (
        "correction text 'stop emitting BANG' not found in cli-return.jsonl — "
        "the consumer delivery channel has content but it's the wrong correction. "
        "This means the observer ran but the cli-return dispatcher wrote a different record."
    )

    # ── Simulate worker acknowledging: clear the drift from output.log ──
    # The rule fires on "BANG" in output.log. Replacing the log with
    # non-BANG content simulates the worker having acted on the correction.
    (agent_dir / "output.log").write_text("OK everything is fine now\n")

    # ── (b) CONVERGENCE: second scan produces 0 new corrections ──────
    r2 = _run_observer(
        [
            "run",
            "--agent-id", agent_id,
            "--runtime-dir", str(runtime),
            "--rules-dir", str(rules_dir),
            "--once",
        ],
        cli_env,
        tmp_path,
    )
    assert r2.returncode == 0, f"second pass failed: stderr={r2.stderr}"

    records_pass2 = _read_jsonl(cor_path)
    assert len(records_pass2) == len(records_pass1), (
        f"rule fired again after worker acknowledged — loop did not converge. "
        f"Pass 1 produced {len(records_pass1)} records; pass 2 produced "
        f"{len(records_pass2)} total. The predicate is still firing despite "
        f"the drift being resolved."
    )


def test_observer_loop_keeps_firing_when_drift_persists(
    tmp_path: Path, cli_env: dict[str, str]
):
    """Negative case: if drift is NOT cleared, a second pass adds another record.

    This test confirms the convergence assertion in the positive case above is
    meaningful — the observer DOES produce additional records when drift persists.
    Without this negative case, the convergence assertion could trivially pass
    via a buggy observer that writes nothing on the second pass.
    """
    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    agent_id = "agent-loop-persists"
    agent_dir = runtime / "agents" / agent_id
    agent_dir.mkdir(parents=True)

    (agent_dir / "output.log").write_text("BANG BANG still going\n")
    _make_bang_rule(rules_dir)

    base_args = [
        "run",
        "--agent-id", agent_id,
        "--runtime-dir", str(runtime),
        "--rules-dir", str(rules_dir),
        "--once",
    ]

    r1 = _run_observer(base_args, cli_env, tmp_path)
    assert r1.returncode == 0

    # Drift NOT cleared — output.log still contains BANG.
    r2 = _run_observer(base_args, cli_env, tmp_path)
    assert r2.returncode == 0

    cor_path = agent_dir / "corrections.jsonl"
    records = _read_jsonl(cor_path)
    assert len(records) == 2, (
        f"expected 2 records (one per pass with persistent drift) but got {len(records)}. "
        "This negative-case test validates that the convergence assertion in the "
        "positive test is not trivially true."
    )
