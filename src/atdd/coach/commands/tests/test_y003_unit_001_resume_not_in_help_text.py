# URN: test:dispatch-ux-defaults-and-primer:multiplexer-primer:Y003-UNIT-001-resume-not-in-help-text
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y003-UNIT-001-resume-not-in-help-text
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y003
# Phase: RED
# Layer: presentation
# Runtime: python
"""Y003-UNIT-001 — '--resume' does not appear in atdd coach --help output.

RED: '--resume' currently appears in the coach CLI --help output. The J6 resume
runner is documented as 'not implemented' in coach.py. Operators who follow the
--help text and attempt --resume RUN_ID get a misleading 'not implemented' error
or silent no-op, making recovery from blocked cold-starts confusing.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_resume_not_in_help_text():
    """atdd coach --help output does not contain '--resume' as a visible option."""
    from atdd.coach.commands import coach

    make_parser = getattr(coach, "_make_coach_parser", None)
    assert make_parser is not None, (
        "_make_coach_parser not found — cannot inspect coach CLI help text (RED)"
    )

    parser = make_parser()
    help_text = parser.format_help()

    assert "--resume" not in help_text, (
        f"'--resume' must NOT appear in 'atdd coach --help' until J6 lands; "
        f"it currently misleads operators into an unimplemented recovery path (RED)\n"
        f"Relevant section: {help_text!r}"
    )


def test_help_contains_recovery_note():
    """atdd coach --help contains a recovery note about re-running atdd coach."""
    from atdd.coach.commands import coach

    make_parser = getattr(coach, "_make_coach_parser", None)
    assert make_parser is not None, (
        "_make_coach_parser not found (RED)"
    )

    parser = make_parser()
    help_text = parser.format_help()

    has_recovery = (
        "Recovery" in help_text
        or "re-run" in help_text.lower()
        or "cold-start is idempotent" in help_text
    )
    assert has_recovery, (
        f"'atdd coach --help' must contain a recovery note (e.g. 'Recovery:' or "
        f"'re-run atdd coach') to guide operators blocked on cold-start failures; "
        f"help text: {help_text!r}"
    )
