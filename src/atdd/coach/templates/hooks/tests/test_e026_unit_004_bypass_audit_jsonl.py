# URN: test:govern-lifecycle:close-substrate-friction-regressions:E026-UNIT-004-bypass-audit-jsonl-written
# Acceptance: acc:govern-lifecycle:E026-UNIT-004-bypass-audit-jsonl-written
# WMBT: wmbt:govern-lifecycle:E026
# Phase: RED
# Layer: backend.unit
"""
AC-UNIT-004: ATDD_BYPASS_REASON set alongside a remaining flag appends a JSON
event to .atdd/bypass-audit.jsonl with fields: timestamp, flag, reason, hook.

RED state: The hooks do not yet write bypass-audit.jsonl. Tests fail because
the audit-logging mechanism has not been implemented.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.platform]

HOOKS_DIR = Path(__file__).resolve().parents[1]
HOOK_PATH = HOOKS_DIR / "pre-push"

_STDIN_NON_MAIN = (
    "refs/heads/feat/x 0000000000000000000000000000000000000001 "
    "refs/heads/feat/x 0000000000000000000000000000000000000000\n"
)

_REQUIRED_JSONL_FIELDS = {"timestamp", "flag", "reason", "hook"}


def _run_hook_with_bypass(tmp_path: Path, flag: str, reason: str) -> Path:
    """Install hook, create .atdd/ dir, run with flag+reason, return jsonl path."""
    atdd_dir = tmp_path / ".atdd"
    atdd_dir.mkdir()

    hook_dest = tmp_path / "pre-push"
    hook_dest.write_bytes(HOOK_PATH.read_bytes())
    hook_dest.chmod(0o755)

    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "CI": "",
        "ATDD_SKIP_PREPUSH_VALIDATE": "1",
        "ATDD_SKIP_VERSION_GATE": "1",
        "ATDD_SKIP_BARE_CHECK": "1",
        "ATDD_BYPASS_REASON": reason,
        flag: "1",
        "ATDD_REPO_ROOT": str(tmp_path),
    }

    subprocess.run(
        [str(hook_dest), "origin", "https://example.com/repo.git"],
        input=_STDIN_NON_MAIN,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env=env,
    )

    return atdd_dir / "bypass-audit.jsonl"


def test_hook_source_contains_jsonl_write_logic():
    """AC-UNIT-004: pre-push hook source must write to bypass-audit.jsonl."""
    text = HOOK_PATH.read_text(encoding="utf-8")
    assert "bypass-audit.jsonl" in text, (
        "pre-push hook does not write to .atdd/bypass-audit.jsonl.\n"
        "Add a block that appends a JSON line when a remaining flag + ATDD_BYPASS_REASON are set."
    )


def test_bypass_audit_jsonl_created_on_bypass(tmp_path: Path):
    """AC-UNIT-004: .atdd/bypass-audit.jsonl is created when ATDD_SKIP_PREPUSH_VALIDATE + reason used."""
    if "bypass-audit.jsonl" not in HOOK_PATH.read_text():
        pytest.skip("bypass-audit.jsonl not yet implemented — RED")

    jsonl_path = _run_hook_with_bypass(tmp_path, "ATDD_SKIP_PREPUSH_VALIDATE", "local stale acceptance")
    assert jsonl_path.exists(), (
        f".atdd/bypass-audit.jsonl was not created at {jsonl_path}.\n"
        "The hook must write an audit event when a bypass flag + ATDD_BYPASS_REASON are used."
    )


def test_bypass_audit_jsonl_contains_valid_json(tmp_path: Path):
    """AC-UNIT-004: each line in bypass-audit.jsonl is valid JSON."""
    if "bypass-audit.jsonl" not in HOOK_PATH.read_text():
        pytest.skip("bypass-audit.jsonl not yet implemented — RED")

    jsonl_path = _run_hook_with_bypass(tmp_path, "ATDD_SKIP_PREPUSH_VALIDATE", "test reason")
    if not jsonl_path.exists():
        pytest.skip("jsonl not created — implementation not yet green")

    for i, line in enumerate(jsonl_path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Line {i} is not valid JSON: {exc}\nContent: {line!r}")


def test_bypass_audit_jsonl_has_required_fields(tmp_path: Path):
    """AC-UNIT-004: each audit event has timestamp, flag, reason, hook fields."""
    if "bypass-audit.jsonl" not in HOOK_PATH.read_text():
        pytest.skip("bypass-audit.jsonl not yet implemented — RED")

    jsonl_path = _run_hook_with_bypass(tmp_path, "ATDD_SKIP_PREPUSH_VALIDATE", "stale acceptance test")
    if not jsonl_path.exists():
        pytest.skip("jsonl not created — implementation not yet green")

    events = [
        json.loads(line)
        for line in jsonl_path.read_text().splitlines()
        if line.strip()
    ]
    assert events, "No events written to bypass-audit.jsonl"

    for event in events:
        missing = _REQUIRED_JSONL_FIELDS - set(event.keys())
        assert not missing, (
            f"Bypass audit event is missing required fields: {missing}\n"
            f"Event: {event}"
        )


def test_bypass_audit_jsonl_records_correct_flag(tmp_path: Path):
    """AC-UNIT-004: the 'flag' field in the audit event matches the bypass flag used."""
    if "bypass-audit.jsonl" not in HOOK_PATH.read_text():
        pytest.skip("bypass-audit.jsonl not yet implemented — RED")

    jsonl_path = _run_hook_with_bypass(tmp_path, "ATDD_SKIP_PREPUSH_VALIDATE", "unit test")
    if not jsonl_path.exists():
        pytest.skip("jsonl not created — implementation not yet green")

    events = [
        json.loads(line)
        for line in jsonl_path.read_text().splitlines()
        if line.strip()
    ]
    flags_recorded = [e.get("flag", "") for e in events]
    assert "ATDD_SKIP_PREPUSH_VALIDATE" in flags_recorded, (
        f"Expected 'ATDD_SKIP_PREPUSH_VALIDATE' in recorded flags, got: {flags_recorded}"
    )


def test_bypass_audit_jsonl_records_correct_reason(tmp_path: Path):
    """AC-UNIT-004: the 'reason' field in the audit event matches ATDD_BYPASS_REASON."""
    if "bypass-audit.jsonl" not in HOOK_PATH.read_text():
        pytest.skip("bypass-audit.jsonl not yet implemented — RED")

    jsonl_path = _run_hook_with_bypass(tmp_path, "ATDD_SKIP_PREPUSH_VALIDATE", "unique-test-reason-xyz")
    if not jsonl_path.exists():
        pytest.skip("jsonl not created — implementation not yet green")

    events = [
        json.loads(line)
        for line in jsonl_path.read_text().splitlines()
        if line.strip()
    ]
    reasons = [e.get("reason", "") for e in events]
    assert "unique-test-reason-xyz" in reasons, (
        f"Expected reason 'unique-test-reason-xyz' in audit events, got: {reasons}"
    )
