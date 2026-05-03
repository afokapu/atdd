"""
Unit tests for `atdd babysit --approve-all-safe` (issue #377).

Behavior under test (Phase 3 of the issue):
  * Sweep all monitored workspaces in scope.
  * Read each surface's screen and run the existing #366 classifier.
  * For every prompt the classifier returns ``auto_approve`` for, send
    ``"1"`` + Enter (the same approval handshake as the per-cycle path).
  * Escalate-class prompts are LEFT alone — never auto-approved.
  * Each approval is logged with ``event="agg_approve"`` and a reason
    starting with ``"agg-approve: "`` so the action is auditable in
    ``orchestration-log.jsonl``.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atdd.coach.commands.babysit import aggregate_approve

pytestmark = [pytest.mark.platform]


_PROMPT_MARKER = "Do you want to proceed?\n❯ 1. Yes\n  2. No\n"


def _backend_with_screens(per_ref: dict[str, str]) -> MagicMock:
    """Backend whose read_screen looks up by ref."""
    backend = MagicMock()
    backend.read_screen.side_effect = lambda ref, lines=80: per_ref[ref]
    return backend


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_aggregate_approve_sweeps_all_safe_prompts(tmp_path: Path):
    """git status, gh pr view (matches read-only file inspection? no — gh isn't
    on the allowlist; use pytest as a known-allow case)."""
    backend = _backend_with_screens(
        {
            "surface:31": "Bash(git status --short)\n" + _PROMPT_MARKER,
            "surface:32": "Bash(pytest -xvs)\n" + _PROMPT_MARKER,
            "surface:33": "Bash(ls -la)\n" + _PROMPT_MARKER,
        }
    )
    log = tmp_path / "log.jsonl"

    result = aggregate_approve(
        backend=backend,
        refs=["surface:31", "surface:32", "surface:33"],
        log_path=log,
    )

    assert result.approved == 3
    assert result.escalated == 0

    # Each ref got a "1"+Enter pair sent.
    sent_calls = [c.args for c in backend.send.call_args_list]
    assert sorted(sent_calls) == [
        ("surface:31", "1"),
        ("surface:32", "1"),
        ("surface:33", "1"),
    ]
    enter_calls = [c.args for c in backend.send_key.call_args_list]
    assert sorted(enter_calls) == [
        ("surface:31", "Enter"),
        ("surface:32", "Enter"),
        ("surface:33", "Enter"),
    ]


def test_aggregate_approve_leaves_escalations_alone(tmp_path: Path):
    """Unknown / dangerous Bash → kept for manual review."""
    backend = _backend_with_screens(
        {
            "surface:31": "Bash(git status)\n" + _PROMPT_MARKER,
            "surface:32": "Bash(curl https://example.com)\n" + _PROMPT_MARKER,
            "surface:33": "Bash(some-novel-cli --flag)\n" + _PROMPT_MARKER,
        }
    )
    log = tmp_path / "log.jsonl"

    result = aggregate_approve(
        backend=backend,
        refs=["surface:31", "surface:32", "surface:33"],
        log_path=log,
    )

    assert result.approved == 1
    assert result.escalated == 2

    # Only the safe surface got approved.
    assert backend.send.call_args_list == [
        (("surface:31", "1"),),
    ] or [c.args for c in backend.send.call_args_list] == [("surface:31", "1")]
    assert backend.send_key.call_args_list[0].args == ("surface:31", "Enter")


def test_aggregate_approve_skips_idle_surfaces(tmp_path: Path):
    """Surfaces with no pending prompt should be no-ops."""
    backend = _backend_with_screens(
        {
            "surface:31": "just some logs, nothing pending\n",
            "surface:32": "Bash(git status)\n" + _PROMPT_MARKER,
        }
    )
    log = tmp_path / "log.jsonl"

    result = aggregate_approve(
        backend=backend,
        refs=["surface:31", "surface:32"],
        log_path=log,
    )

    assert result.approved == 1
    assert result.escalated == 0
    assert [c.args for c in backend.send.call_args_list] == [("surface:32", "1")]


def test_aggregate_approve_skips_violations(tmp_path: Path):
    """A `.atdd/` hand-edit is a violation, never auto-approved."""
    backend = _backend_with_screens(
        {
            "surface:31": "Edit(.atdd/manifest.yaml)\n" + _PROMPT_MARKER,
        }
    )
    log = tmp_path / "log.jsonl"

    result = aggregate_approve(
        backend=backend,
        refs=["surface:31"],
        log_path=log,
    )

    assert result.approved == 0
    backend.send.assert_not_called()


# ---------------------------------------------------------------------------
# Telemetry — every approval is logged with rule attribution
# ---------------------------------------------------------------------------


def test_aggregate_approve_logs_each_approval_with_reason(tmp_path: Path):
    backend = _backend_with_screens(
        {
            "surface:31": "Bash(git status)\n" + _PROMPT_MARKER,
            "surface:32": "Bash(pytest)\n" + _PROMPT_MARKER,
        }
    )
    log = tmp_path / "log.jsonl"

    aggregate_approve(
        backend=backend,
        refs=["surface:31", "surface:32"],
        log_path=log,
    )

    events = [json.loads(line) for line in log.read_text().splitlines()]
    approvals = [e for e in events if e.get("event") == "agg_approve"]
    assert len(approvals) == 2

    workspaces = sorted(e["workspace"] for e in approvals)
    assert workspaces == ["surface:31", "surface:32"]
    for e in approvals:
        assert e["reason"].startswith("agg-approve: ")
        assert e["pattern"].startswith("COACH-BABYSIT-")


def test_aggregate_approve_returns_summary(tmp_path: Path):
    backend = _backend_with_screens(
        {
            "surface:31": "Bash(git status)\n" + _PROMPT_MARKER,
            "surface:32": "Bash(curl https://x)\n" + _PROMPT_MARKER,
        }
    )
    log = tmp_path / "log.jsonl"

    result = aggregate_approve(
        backend=backend,
        refs=["surface:31", "surface:32"],
        log_path=log,
    )

    assert result.approved == 1
    assert result.escalated == 1
    # The struct also exposes the per-ref disposition for later inspection.
    assert "surface:31" in result.approvals_by_ref
    assert result.approvals_by_ref["surface:31"].startswith("COACH-BABYSIT-")
    assert "surface:32" in result.escalations_by_ref


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------


def test_aggregate_approve_empty_refs_is_noop(tmp_path: Path):
    backend = MagicMock()
    log = tmp_path / "log.jsonl"

    result = aggregate_approve(backend=backend, refs=[], log_path=log)

    assert result.approved == 0
    assert result.escalated == 0
    backend.read_screen.assert_not_called()
    backend.send.assert_not_called()
