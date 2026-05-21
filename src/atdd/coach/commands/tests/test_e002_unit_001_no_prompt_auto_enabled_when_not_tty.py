# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:E002-UNIT-001-no-prompt-auto-enabled-when-not-tty
# Acceptance: acc:dispatch-ux-defaults-and-primer:E002-UNIT-001-no-prompt-auto-enabled-when-not-tty
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E002
# Phase: RED
# Layer: application
# Runtime: python
"""E002-UNIT-001 — resolve_no_prompt returns True when stdin is not a TTY and no explicit flag.

RED: resolve_no_prompt does not exist in coach.py. The coach currently
evaluates should_prompt_for_models() which calls _isatty() inline, but there
is no explicit resolve_no_prompt helper that the CLI can call to set the
no_prompt flag before constructing CoachConfig. Non-TTY invocations can hang
on the persona prompt indefinitely.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_no_prompt_true_when_not_tty():
    """resolve_no_prompt returns True when isatty=False and no explicit flag."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_no_prompt", None)
    assert fn is not None, (
        "coach.resolve_no_prompt is not implemented — "
        "auto-no-prompt for non-TTY contexts is missing (RED)"
    )

    result = fn(explicit_flag=None, isatty=False)
    assert result is True, (
        f"expected True (no-prompt enabled) when isatty=False, got {result!r}"
    )


def test_prompt_shown_when_tty_and_no_explicit_flag():
    """resolve_no_prompt returns False when isatty=True and no explicit flag (prompt shown)."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_no_prompt", None)
    assert fn is not None, (
        "coach.resolve_no_prompt is not implemented (RED)"
    )

    result = fn(explicit_flag=None, isatty=True)
    assert result is False, (
        f"expected False (prompt shown) when isatty=True, got {result!r}"
    )


def test_explicit_true_wins_over_tty():
    """explicit_flag=True forces no-prompt even in a TTY."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_no_prompt", None)
    assert fn is not None, "coach.resolve_no_prompt is not implemented (RED)"

    result = fn(explicit_flag=True, isatty=True)
    assert result is True, (
        f"explicit_flag=True must override isatty=True; got {result!r}"
    )


def test_explicit_false_wins_over_non_tty():
    """explicit_flag=False forces the prompt even when stdin is not a TTY."""
    from atdd.coach.commands import coach

    fn = getattr(coach, "resolve_no_prompt", None)
    assert fn is not None, "coach.resolve_no_prompt is not implemented (RED)"

    result = fn(explicit_flag=False, isatty=False)
    assert result is False, (
        f"explicit_flag=False must override isatty=False; got {result!r}"
    )
