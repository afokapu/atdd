"""
Unit tests for babysit token-count alert (issue #378, Phase 2).

Babysit reads each workspace's token count and emits a `token_threshold` alert
when it crosses the configured threshold (default 400_000, override via
``babysit.token_alert_threshold`` in ``.atdd/config.yaml``).

Source mechanism: Decision 6 — `claude --print-context-status` JSON. The
fallback is None ("—" in the dashboard) when the binary or the output is
unavailable.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from atdd.coach.commands.babysit import (
    DEFAULT_TOKEN_ALERT_THRESHOLD,
    BabysitDecision,
    WorkspaceState,
    check_token_threshold,
    load_token_alert_threshold,
    read_token_count,
)

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# DEFAULT_TOKEN_ALERT_THRESHOLD
# ---------------------------------------------------------------------------


def test_default_threshold_is_400k():
    assert DEFAULT_TOKEN_ALERT_THRESHOLD == 400_000


# ---------------------------------------------------------------------------
# load_token_alert_threshold
# ---------------------------------------------------------------------------


def test_load_threshold_uses_default_when_no_config(tmp_path: Path):
    assert load_token_alert_threshold(repo_root=tmp_path) == DEFAULT_TOKEN_ALERT_THRESHOLD


def test_load_threshold_reads_atdd_config(tmp_path: Path):
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "babysit:\n  token_alert_threshold: 250000\n"
    )
    assert load_token_alert_threshold(repo_root=tmp_path) == 250_000


def test_load_threshold_falls_back_when_config_malformed(tmp_path: Path):
    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text("this is: [not valid yaml")
    # Malformed config falls back silently to the default.
    assert load_token_alert_threshold(repo_root=tmp_path) == DEFAULT_TOKEN_ALERT_THRESHOLD


# ---------------------------------------------------------------------------
# check_token_threshold
# ---------------------------------------------------------------------------


def test_check_returns_none_below_threshold():
    assert check_token_threshold(token_count=100_000, threshold=400_000) is None


def test_check_returns_none_when_unavailable():
    assert check_token_threshold(token_count=None, threshold=400_000) is None


def test_check_alerts_when_above_threshold():
    decision = check_token_threshold(token_count=420_000, threshold=400_000)
    assert decision is not None
    assert decision.action == "escalate"
    assert "420" in (decision.matched + decision.reason)
    assert "400" in (decision.matched + decision.reason)


def test_check_alerts_at_exactly_threshold():
    decision = check_token_threshold(token_count=400_000, threshold=400_000)
    assert decision is not None
    assert decision.action == "escalate"


# ---------------------------------------------------------------------------
# read_token_count
# ---------------------------------------------------------------------------


def test_read_token_count_returns_none_when_binary_missing():
    backend = MagicMock()
    with patch(
        "atdd.coach.commands.babysit.subprocess.run",
        side_effect=FileNotFoundError("claude not on PATH"),
    ):
        assert read_token_count(backend, workspace_ref="ws:1") is None


def test_read_token_count_returns_none_on_non_json_output():
    backend = MagicMock()
    fake_result = MagicMock(stdout="not json", returncode=0)
    with patch("atdd.coach.commands.babysit.subprocess.run", return_value=fake_result):
        assert read_token_count(backend, workspace_ref="ws:1") is None


def test_read_token_count_parses_claude_output():
    backend = MagicMock()
    fake_result = MagicMock(
        stdout=json.dumps({"context_used_tokens": 412_345}),
        returncode=0,
    )
    with patch("atdd.coach.commands.babysit.subprocess.run", return_value=fake_result):
        assert read_token_count(backend, workspace_ref="ws:1") == 412_345


# ---------------------------------------------------------------------------
# Integration: process_workspace surfaces token alert
# ---------------------------------------------------------------------------


def test_process_workspace_emits_token_alert_event(tmp_path: Path):
    """When a workspace's token count crosses threshold, an event is logged
    and the decision is surfaced to the caller."""
    from atdd.coach.commands.babysit import process_workspace

    log = tmp_path / "log.jsonl"
    backend = MagicMock()
    backend.read_screen.return_value = "boring idle screen"

    state = WorkspaceState(ref="ws:1")

    with patch(
        "atdd.coach.commands.babysit.read_token_count",
        return_value=500_000,
    ):
        decision = process_workspace(
            backend, state, 15, 30,
            log_path=log,
            token_alert_threshold=400_000,
        )

    assert decision.action == "escalate"
    assert "token" in (decision.matched + decision.reason).lower()
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(e["event"] == "token_threshold" for e in events)


def test_process_workspace_no_alert_below_threshold(tmp_path: Path):
    from atdd.coach.commands.babysit import process_workspace

    log = tmp_path / "log.jsonl"
    backend = MagicMock()
    backend.read_screen.return_value = "boring idle screen"

    state = WorkspaceState(ref="ws:1")

    with patch(
        "atdd.coach.commands.babysit.read_token_count",
        return_value=100_000,
    ):
        decision = process_workspace(
            backend, state, 15, 30,
            log_path=log,
            token_alert_threshold=400_000,
        )

    assert decision.action != "escalate" or "token" not in decision.reason.lower()
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert not any(e["event"] == "token_threshold" for e in events)
