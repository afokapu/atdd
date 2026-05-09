# URN: test:observe-and-correct:observer-runtime-and-rules:P001-SMOKE-001-observer-cli-e2e
# Acceptance: acc:observe-and-correct:P001-UNIT-001-observer-run-tails-log
# Acceptance: acc:observe-and-correct:P001-UNIT-002-correction-fires-and-writes
# Acceptance: acc:observe-and-correct:P001-UNIT-003-attach-prints-recent-observations
# Acceptance: acc:observe-and-correct:P001-UNIT-006-rule-load-error-surfaced
# WMBT: wmbt:observe-and-correct:P001
# Phase: SMOKE
# Layer: backend.integration
"""P001-SMOKE-001 — exercise the `atdd observer` CLI end-to-end.

Spawns the real `atdd observer` entry point (via `python3 -m atdd`)
against a tmp runtime root and a tmp rules dir. Verifies the CLI
discovers rules from disk, fires synthetic detections from a real
output.log, persists corrections.jsonl in schema-valid form, and
surfaces malformed rules through the meta:rule_load_error path.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import jsonschema
import pytest

import atdd

pytestmark = [pytest.mark.platform]


SRC_ROOT = Path(__file__).resolve().parents[4]
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
CORRECTION_SCHEMA = ATDD_PKG_DIR / "coach" / "schemas" / "correction.schema.json"


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


def _run(args: list[str], env: dict[str, str], cwd: Path):
    return subprocess.run(
        ["python3", "-m", "atdd", "observer", *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_observer_cli_discovers_rules_fires_correction_writes_jsonl(
    tmp_path: Path, cli_env: dict[str, str]
):
    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    agent_id = "agent-smoke-L1"
    agent_dir = runtime / "agents" / agent_id
    agent_dir.mkdir(parents=True)
    (agent_dir / "output.log").write_text("BANG! we said BANG\n")

    # A rule that fires when the output.log mentions BANG. The rule_id
    # is bind_rule()-resolvable (it's a real rule from
    # orchestration.convention.yaml — borrowed for test purposes).
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

    # `atdd observer run --once` does a single pass and exits.
    r = _run(
        [
            "run",
            "--agent-id",
            agent_id,
            "--runtime-dir",
            str(runtime),
            "--rules-dir",
            str(rules_dir),
            "--once",
        ],
        cli_env,
        tmp_path,
    )
    assert r.returncode == 0, f"observer run failed: stderr={r.stderr}"

    cor_path = agent_dir / "corrections.jsonl"
    assert cor_path.exists(), "observer must persist corrections.jsonl on disk"
    records = _read_jsonl(cor_path)
    assert len(records) == 1
    schema = json.loads(CORRECTION_SCHEMA.read_text())
    jsonschema.validate(records[0], schema)
    assert records[0]["correction_text"] == "stop emitting BANG"
    assert records[0]["injection_method"] == "cli-return"

    # The cli-return dispatcher must materialize the per-agent
    # return-channel file too.
    return_channel = agent_dir / "cli-return.jsonl"
    assert return_channel.exists()
    return_recs = _read_jsonl(return_channel)
    assert any(rec.get("correction_text") == "stop emitting BANG" for rec in return_recs)

    # `atdd observer attach` prints the persisted observation.
    r2 = _run(
        ["attach", "--agent-id", agent_id, "--runtime-dir", str(runtime)],
        cli_env,
        tmp_path,
    )
    assert r2.returncode == 0
    assert "stop emitting BANG" in r2.stdout
    assert "coach.orchestration.read-only-git-diagnostics" in r2.stdout


def test_observer_cli_surfaces_malformed_rule_via_meta_load_error(
    tmp_path: Path, cli_env: dict[str, str]
):
    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)
    agent_id = "agent-smoke-L1-broken"

    (rules_dir / "00-broken.yaml").write_text(
        """
trigger:
  type: log_regex
  pattern: ".*x.*"
correction_text: "missing rule_id"
"""
    )

    r = _run(
        [
            "run",
            "--agent-id",
            agent_id,
            "--runtime-dir",
            str(runtime),
            "--rules-dir",
            str(rules_dir),
            "--once",
        ],
        cli_env,
        tmp_path,
    )
    assert r.returncode == 0
    assert "00-broken.yaml" in r.stderr, (
        f"stderr should warn about the malformed rule; got: {r.stderr!r}"
    )

    cor_path = runtime / "agents" / agent_id / "corrections.jsonl"
    assert cor_path.exists()
    recs = _read_jsonl(cor_path)
    assert any(
        rec.get("meta") == "rule_load_error"
        and "00-broken.yaml" in rec.get("rule_path", "")
        for rec in recs
    ), f"expected meta:rule_load_error in {recs}"
