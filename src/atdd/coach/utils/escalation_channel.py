"""Parse and validate ``--escalation-channel`` values for ``atdd coach``.

Per spec §5.1/§9, `--escalation-channel` accepts three channel types:

  * file          → ``file:<path>`` or bare ``<path>`` shortcut
  * slack-webhook → ``slack-webhook:<https-url>``
  * github-issue  → ``gh-issue:<owner>/<repo>#<n>`` or ``gh-issue:#<n>``

The value format was previously undefined; the CLI accepted any string
and behaviour fell through to a default file handler by coincidence.
This module makes the contract explicit and rejects malformed values at
argparse-parse time.

See issue #615.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from typing import Optional, Tuple


# A bare-string GitHub repo shorthand: "owner/repo#123".
_GH_FULL_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)/([A-Za-z0-9._-]+)#(\d+)$")

# Issue-only shorthand using the current repo: "#123".
_GH_ISSUE_ONLY_RE = re.compile(r"^#(\d+)$")

# Slack webhook URL must be https on hooks.slack.com.
_SLACK_URL_RE = re.compile(r"^https://hooks\.slack\.com/services/[A-Za-z0-9/_-]+$")


ChannelType = str  # one of: "file", "slack-webhook", "github-issue"


@dataclass(frozen=True)
class EscalationChannel:
    """Parsed escalation-channel value."""

    channel_type: ChannelType
    payload: str

    def __str__(self) -> str:  # pragma: no cover - cosmetic only
        return f"{self.channel_type}:{self.payload}"


_VALID_FORMS_HELP = (
    "Valid forms:\n"
    "  file:<path>                  (e.g. file:./.atdd/escalations.log)\n"
    "  <path>                       (bare path, treated as file)\n"
    "  slack-webhook:<https-url>    (e.g. slack-webhook:https://hooks.slack.com/services/X/Y/Z)\n"
    "  gh-issue:owner/repo#N        (e.g. gh-issue:afokapu/atdd#999)\n"
    "  gh-issue:#N                  (e.g. gh-issue:#999 — uses current repo)"
)


def parse_escalation_channel(value: str) -> EscalationChannel:
    """Parse and validate an ``--escalation-channel`` value.

    Args:
        value: Raw string from the CLI flag.

    Returns:
        ``EscalationChannel(channel_type, payload)``.

    Raises:
        argparse.ArgumentTypeError: on any malformed value, with the three
        valid forms in the error message.
    """
    if not value or not value.strip():
        raise argparse.ArgumentTypeError(
            "--escalation-channel value cannot be empty.\n\n" + _VALID_FORMS_HELP
        )

    raw = value.strip()

    # Explicit prefixes — checked in declared order so ambiguities resolve
    # to the most specific form first.
    if raw.startswith("slack-webhook:"):
        payload = raw[len("slack-webhook:"):]
        if not _SLACK_URL_RE.match(payload):
            raise argparse.ArgumentTypeError(
                f"slack-webhook payload must be an https://hooks.slack.com/services/... URL; got {payload!r}.\n\n"
                + _VALID_FORMS_HELP
            )
        return EscalationChannel(channel_type="slack-webhook", payload=payload)

    if raw.startswith("gh-issue:"):
        payload = raw[len("gh-issue:"):]
        if _GH_FULL_RE.match(payload) or _GH_ISSUE_ONLY_RE.match(payload):
            return EscalationChannel(channel_type="github-issue", payload=payload)
        raise argparse.ArgumentTypeError(
            f"gh-issue payload must be 'owner/repo#N' or '#N'; got {payload!r}.\n\n"
            + _VALID_FORMS_HELP
        )

    if raw.startswith("file:"):
        payload = raw[len("file:"):]
        if not payload:
            raise argparse.ArgumentTypeError(
                "file: prefix requires a non-empty path.\n\n" + _VALID_FORMS_HELP
            )
        return EscalationChannel(channel_type="file", payload=payload)

    # Bare-path shortcut: anything else without a known prefix is treated as
    # a file path. We intentionally accept this for backwards compatibility
    # with anyone using the prior undocumented "looks like a path" branch.
    # Disambiguate by rejecting values that LOOK like a malformed prefix:
    if ":" in raw and not raw.startswith((".", "/", "~")):
        prefix = raw.split(":", 1)[0]
        if prefix in ("slack-webhook", "gh-issue", "file"):
            # Already handled above; this branch means the payload was empty/invalid.
            raise argparse.ArgumentTypeError(
                f"{prefix}: prefix is recognised but the payload is invalid.\n\n"
                + _VALID_FORMS_HELP
            )
        raise argparse.ArgumentTypeError(
            f"Unrecognised channel prefix {prefix!r}.\n\n" + _VALID_FORMS_HELP
        )

    return EscalationChannel(channel_type="file", payload=raw)


def channel_help_epilog() -> str:
    """Return the human-readable form spec, suitable for argparse epilog."""
    return "Escalation channel value formats:\n" + _VALID_FORMS_HELP


def validate_escalation_channel_arg(value: str) -> str:
    """argparse ``type=`` callable: validate the format, return the raw string.

    Use this as the ``type=`` for ``--escalation-channel`` so malformed values
    are rejected at parse time. Downstream consumers continue to receive a
    plain string (the same value the user passed) for backwards compatibility
    with code that hasn't migrated to the parsed dataclass yet.
    """
    parse_escalation_channel(value)
    return value
