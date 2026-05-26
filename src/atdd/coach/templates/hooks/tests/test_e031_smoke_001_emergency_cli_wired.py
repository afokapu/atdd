# URN: test:govern-lifecycle:close-substrate-friction-regressions:E031-SMOKE-001-emergency-cli-wired-in-atdd
# Acceptance: acc:govern-lifecycle:E031-SMOKE-001-emergency-cli-wired-in-atdd
# WMBT: wmbt:govern-lifecycle:E031
# Phase: SMOKE
# Layer: backend.integration
"""
AC-SMOKE-001: atdd emergency --reason <text> is wired in the live CLI and creates
.atdd/EMERGENCY_BYPASS and .atdd/emergency-audit.jsonl in a real git repo.

Drives the real python3 -m atdd CLI entry point (with src/ on PYTHONPATH so the
source version is used regardless of what is installed) against a temporary git
repository with a .atdd/ directory, verifying CLI wiring and file outputs end-to-end.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

_SRC_DIR = Path(__file__).resolve().parents[5]  # src/


def _src_path() -> str:
    return str(_SRC_DIR)


def _make_atdd_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
        check=True, capture_output=True,
    )
    (tmp_path / ".atdd").mkdir()
    return tmp_path


def test_emergency_cli_wired_and_creates_bypass_file(tmp_path: Path):
    """AC-SMOKE-001: atdd emergency --reason text is wired in the live CLI."""
    repo = _make_atdd_repo(tmp_path)

    env = os.environ.copy()
    env["PYTHONPATH"] = _src_path() + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, "-m", "atdd", "emergency", "--reason", "smoke test bypass"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, (
        f"atdd emergency returned non-zero exit code {result.returncode}.\n"
        f"stderr: {result.stderr}\n"
        "The 'emergency' subcommand must be wired in atdd/cli.py."
    )

    bypass_file = repo / ".atdd" / "EMERGENCY_BYPASS"
    assert bypass_file.exists(), (
        ".atdd/EMERGENCY_BYPASS was not created.\n"
        "Check that cli.py routes 'emergency' to cmd_emergency()."
    )
    assert "smoke test bypass" in bypass_file.read_text(encoding="utf-8"), (
        "EMERGENCY_BYPASS does not contain the reason string."
    )

    audit_log = repo / ".atdd" / "emergency-audit.jsonl"
    assert audit_log.exists(), ".atdd/emergency-audit.jsonl was not created."

    lines = [ln for ln in audit_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, ".atdd/emergency-audit.jsonl is empty"

    record = json.loads(lines[-1])
    assert record.get("reason") == "smoke test bypass", (
        f"Audit record reason mismatch: {record}"
    )
