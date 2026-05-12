# Acceptance: acc:integration-hardening:E001-UNIT-NNN-escalation-channel-value-spec  # placeholder
"""Unit tests for ``parse_escalation_channel`` (#615)."""
from __future__ import annotations

import argparse

import pytest

from atdd.coach.utils.escalation_channel import (
    EscalationChannel,
    channel_help_epilog,
    parse_escalation_channel,
    validate_escalation_channel_arg,
)


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


def test_slack_webhook_valid() -> None:
    result = parse_escalation_channel(
        "slack-webhook:https://hooks.slack.com/services/T00/B00/abc"
    )
    assert result == EscalationChannel(
        channel_type="slack-webhook",
        payload="https://hooks.slack.com/services/T00/B00/abc",
    )


def test_slack_webhook_must_be_https() -> None:
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        parse_escalation_channel("slack-webhook:http://hooks.slack.com/services/X/Y/Z")
    assert "slack-webhook" in str(exc.value)


def test_slack_webhook_wrong_host_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_escalation_channel("slack-webhook:https://example.com/webhook")


# ---------------------------------------------------------------------------
# GitHub issue
# ---------------------------------------------------------------------------


def test_gh_issue_full_form() -> None:
    result = parse_escalation_channel("gh-issue:afokapu/atdd#999")
    assert result == EscalationChannel(channel_type="github-issue", payload="afokapu/atdd#999")


def test_gh_issue_short_form() -> None:
    result = parse_escalation_channel("gh-issue:#42")
    assert result == EscalationChannel(channel_type="github-issue", payload="#42")


def test_gh_issue_invalid_form_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_escalation_channel("gh-issue:not-a-number")


def test_gh_issue_missing_hash_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_escalation_channel("gh-issue:owner/repo")


# ---------------------------------------------------------------------------
# File (explicit prefix and bare-path shortcut)
# ---------------------------------------------------------------------------


def test_file_prefix() -> None:
    result = parse_escalation_channel("file:./errors.log")
    assert result == EscalationChannel(channel_type="file", payload="./errors.log")


def test_file_prefix_absolute() -> None:
    result = parse_escalation_channel("file:/var/log/atdd.log")
    assert result == EscalationChannel(channel_type="file", payload="/var/log/atdd.log")


def test_file_prefix_empty_payload_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_escalation_channel("file:")


def test_bare_relative_path_treated_as_file() -> None:
    result = parse_escalation_channel("./errors.log")
    assert result == EscalationChannel(channel_type="file", payload="./errors.log")


def test_bare_absolute_path_treated_as_file() -> None:
    result = parse_escalation_channel("/var/log/atdd.log")
    assert result == EscalationChannel(channel_type="file", payload="/var/log/atdd.log")


def test_bare_simple_name_treated_as_file() -> None:
    result = parse_escalation_channel("errors.log")
    assert result == EscalationChannel(channel_type="file", payload="errors.log")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_string_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_escalation_channel("")


def test_whitespace_only_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_escalation_channel("   ")


def test_unknown_prefix_rejected() -> None:
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        parse_escalation_channel("pagerduty:foo")
    assert "pagerduty" in str(exc.value)


def test_error_messages_include_valid_forms() -> None:
    """All error messages must end with the three valid forms reference."""
    with pytest.raises(argparse.ArgumentTypeError) as exc:
        parse_escalation_channel("garbage:invalid")
    msg = str(exc.value)
    assert "file:" in msg
    assert "slack-webhook:" in msg
    assert "gh-issue:" in msg


# ---------------------------------------------------------------------------
# Argparse adapter
# ---------------------------------------------------------------------------


def test_validate_arg_returns_raw_string_on_success() -> None:
    """argparse-facing wrapper returns the raw string (not the dataclass)."""
    raw = "slack-webhook:https://hooks.slack.com/services/T/B/x"
    assert validate_escalation_channel_arg(raw) == raw


def test_validate_arg_raises_on_invalid() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        validate_escalation_channel_arg("bad-prefix:nope")


# ---------------------------------------------------------------------------
# Help epilog
# ---------------------------------------------------------------------------


def test_epilog_lists_all_three_forms() -> None:
    text = channel_help_epilog()
    assert "file:<path>" in text
    assert "slack-webhook:" in text
    assert "gh-issue:" in text
