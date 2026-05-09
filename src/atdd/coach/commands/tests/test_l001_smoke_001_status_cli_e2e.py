# URN: test:observe-and-correct:observer-operator-surface:L001-SMOKE-001-status-cli-e2e
# Acceptance: acc:observe-and-correct:L001-UNIT-001-status-prints-per-surface-table
# WMBT: wmbt:observe-and-correct:L001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""L001-SMOKE-001 — exercise `atdd observer status` end-to-end against
a real `.atdd/runtime/agents/*/` tree on disk. Verifies the absorbed
dashboard machinery works against actual heartbeat.json / context.json
files, not just unit fixtures.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _seed_agent(
    runtime: Path, *, agent_id: str, phase: str, issue: int,
    heartbeat_offset_s: int, token_count: int | None = None,
) -> None:
    agent_dir = runtime / "agents" / agent_id
    agent_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    hb = {
        "pid": 12345,
        "observed_at": _iso_z(now - timedelta(seconds=heartbeat_offset_s)),
        "status": "running",
    }
    if token_count is not None:
        hb["token_count"] = token_count
    (agent_dir / "heartbeat.json").write_text(json.dumps(hb))
    (agent_dir / "context.json").write_text(
        json.dumps({"phase": phase, "issue": issue, "wmbt_urn": "wmbt:x:R001"})
    )


def test_observer_status_cli_renders_real_runtime_tree(tmp_path: Path):
    """Spawn `python -m atdd.cli observer status` against a tmp runtime
    and assert the rendered table contains every seeded agent."""
    runtime = tmp_path / ".atdd" / "runtime"
    _seed_agent(runtime, agent_id="agent-X", phase="RED", issue=515, heartbeat_offset_s=14)
    _seed_agent(runtime, agent_id="agent-Y", phase="GREEN", issue=516, heartbeat_offset_s=82)
    _seed_agent(
        runtime, agent_id="agent-Z", phase="SMOKE",
        issue=517, heartbeat_offset_s=16 * 60,  # past stale threshold
    )

    repo_src = Path(__file__).resolve().parents[4]
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{repo_src}{os.pathsep}{existing}" if existing else str(repo_src)
    )
    env["ATDD_RUNTIME_ROOT"] = str(runtime)

    result = subprocess.run(
        [sys.executable, "-m", "atdd.cli", "observer", "status"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, (
        f"non-zero exit: {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    out = result.stdout
    assert "ATDD Dashboard" in out
    for token in ("agent-X", "agent-Y", "agent-Z", "#515", "#516", "#517"):
        assert token in out, f"missing {token!r} from CLI output:\n{out}"
    # Stale agent past the warn threshold reports STALLED
    assert "STALLED" in out
