# URN: test:dispatch-ux-defaults-and-primer:multiplexer-primer:Y003-UNIT-002-resume-flag-removed-or-hidden
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y003-UNIT-002-resume-flag-removed-or-hidden
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y003
# Phase: RED
# Layer: presentation
# Runtime: python
"""Y003-UNIT-002 — '--resume' is removed from the argparse definition or marked SUPPRESS.

RED: The coach.py argparse parser defines '--resume' with a visible help string
('Carried for #J6 resume runner; J1 parses but does not reconstruct.'). This
appears in --help and confuses operators into attempting a not-implemented path.
"""
from __future__ import annotations

import argparse

import pytest

pytestmark = [pytest.mark.platform]


def test_resume_action_removed_or_suppressed():
    """The --resume argument is either removed or marked argparse.SUPPRESS."""
    from atdd.coach.commands import coach

    make_parser = getattr(coach, "_make_coach_parser", None)
    assert make_parser is not None, (
        "_make_coach_parser not found — cannot inspect --resume action (RED)"
    )

    parser = make_parser()
    option_map = {
        opt: action
        for action in parser._actions
        for opt in (action.option_strings or [])
    }

    if "--resume" not in option_map:
        # Removed entirely — acceptable.
        return

    resume_action = option_map["--resume"]
    assert resume_action.help == argparse.SUPPRESS, (
        f"'--resume' must be removed or have help=argparse.SUPPRESS; "
        f"current help={resume_action.help!r} (RED — operators see unimplemented flag)"
    )
