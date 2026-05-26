# URN: test:govern-lifecycle:close-substrate-friction-regressions:E031-UNIT-001-emergency-command-creates-bypass-file
# Acceptance: acc:govern-lifecycle:E031-UNIT-001-emergency-command-creates-bypass-file
# WMBT: wmbt:govern-lifecycle:E031
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-001: atdd emergency --reason "<text>" creates .atdd/EMERGENCY_BYPASS with
timestamp and reason, and appends a JSON audit record to .atdd/emergency-audit.jsonl.

RED state: atdd.coach.commands.emergency module does not exist yet.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]


def test_emergency_module_is_importable():
    """AC-UNIT-001: atdd.coach.commands.emergency is importable."""
    try:
        from atdd.coach.commands import emergency  # noqa: F401
    except ImportError as exc:
        pytest.fail(
            f"atdd.coach.commands.emergency is not importable: {exc}\n"
            "Create src/atdd/coach/commands/emergency.py with cmd_emergency()."
        )


def test_cmd_emergency_creates_bypass_file(tmp_path: Path):
    """AC-UNIT-001: cmd_emergency creates .atdd/EMERGENCY_BYPASS in the repo root."""
    try:
        from atdd.coach.commands.emergency import cmd_emergency
    except ImportError:
        pytest.skip("emergency module not yet implemented — RED")

    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()

    cmd_emergency(reason="test emergency", repo_root=tmp_path)

    bypass_file = atdd_dir / "EMERGENCY_BYPASS"
    assert bypass_file.exists(), (
        ".atdd/EMERGENCY_BYPASS was not created.\n"
        "cmd_emergency must write this file so hooks can detect active emergency bypass."
    )

    content = bypass_file.read_text(encoding="utf-8")
    assert "test emergency" in content, (
        f".atdd/EMERGENCY_BYPASS does not contain the reason string.\n"
        f"Content: {content!r}"
    )


def test_cmd_emergency_bypass_file_has_timestamp(tmp_path: Path):
    """AC-UNIT-001: EMERGENCY_BYPASS contains an ISO 8601 timestamp."""
    try:
        from atdd.coach.commands.emergency import cmd_emergency
    except ImportError:
        pytest.skip("emergency module not yet implemented — RED")

    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()

    before = time.time()
    cmd_emergency(reason="timestamp test", repo_root=tmp_path)
    after = time.time()

    bypass_file = atdd_dir / "EMERGENCY_BYPASS"
    content = bypass_file.read_text(encoding="utf-8")
    assert "T" in content or "2026" in content, (
        "EMERGENCY_BYPASS should contain a timestamp (e.g. 2026-05-26T...).\n"
        f"Got: {content!r}"
    )

    mtime = bypass_file.stat().st_mtime
    assert before <= mtime <= after + 2, (
        f"Bypass file mtime {mtime} is outside the expected window [{before}, {after+2}]."
    )


def test_cmd_emergency_appends_to_audit_log(tmp_path: Path):
    """AC-UNIT-004: cmd_emergency appends a valid JSON line to .atdd/emergency-audit.jsonl."""
    try:
        from atdd.coach.commands.emergency import cmd_emergency
    except ImportError:
        pytest.skip("emergency module not yet implemented — RED")

    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()

    cmd_emergency(reason="infra outage", repo_root=tmp_path)

    audit_log = atdd_dir / "emergency-audit.jsonl"
    assert audit_log.exists(), (
        ".atdd/emergency-audit.jsonl was not created.\n"
        "cmd_emergency must append an audit record for every invocation."
    )

    lines = [ln for ln in audit_log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, ".atdd/emergency-audit.jsonl is empty"

    record = json.loads(lines[-1])
    assert "timestamp" in record, f"Audit record missing 'timestamp': {record}"
    assert "reason" in record, f"Audit record missing 'reason': {record}"
    assert record["reason"] == "infra outage", (
        f"Expected reason 'infra outage', got {record['reason']!r}"
    )


def test_cmd_emergency_requires_non_empty_reason(tmp_path: Path):
    """AC-UNIT-001: cmd_emergency raises ValueError when reason is empty or blank."""
    try:
        from atdd.coach.commands.emergency import cmd_emergency
    except ImportError:
        pytest.skip("emergency module not yet implemented — RED")

    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()

    with pytest.raises((ValueError, SystemExit)):
        cmd_emergency(reason="", repo_root=tmp_path)

    with pytest.raises((ValueError, SystemExit)):
        cmd_emergency(reason="   ", repo_root=tmp_path)
