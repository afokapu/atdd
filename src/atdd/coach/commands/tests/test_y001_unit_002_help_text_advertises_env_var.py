# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:Y001-UNIT-002-help-text-advertises-env-var
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y001-UNIT-002-help-text-advertises-env-var
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y001
# Phase: RED
# Layer: presentation
# Runtime: python
"""Y001-UNIT-002 — atdd coach --help mentions ATDD_WORKER_READY_TIMEOUT and the default 30.

RED: The coach CLI parser does not mention ATDD_WORKER_READY_TIMEOUT in any
visible text. Operators who encounter WorkerReadinessTimeout have no discovery
path for the env var without reading source code.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_help_text_contains_env_var_name():
    """The coach CLI help output mentions ATDD_WORKER_READY_TIMEOUT."""
    from atdd.coach.commands import coach

    make_parser = getattr(coach, "_make_coach_parser", None)
    assert make_parser is not None, (
        "_make_coach_parser not found — cannot inspect coach CLI help text (RED)"
    )

    parser = make_parser()
    help_text = parser.format_help()

    assert "ATDD_WORKER_READY_TIMEOUT" in help_text, (
        f"ATDD_WORKER_READY_TIMEOUT must appear in 'atdd coach --help'; "
        f"it is not visible to operators who need to extend the timeout (RED)\n"
        f"Help text: {help_text!r}"
    )


def test_help_text_contains_default_30():
    """The coach CLI help output shows the default value '30' near the env var."""
    from atdd.coach.commands import coach

    make_parser = getattr(coach, "_make_coach_parser", None)
    assert make_parser is not None, (
        "_make_coach_parser not found (RED)"
    )

    parser = make_parser()
    help_text = parser.format_help()

    # Rough proximity check — both "ATDD_WORKER_READY_TIMEOUT" and "30" appear
    # in the help text (they may be on different lines of the epilog).
    has_env_var = "ATDD_WORKER_READY_TIMEOUT" in help_text
    has_default = "30" in help_text

    assert has_env_var and has_default, (
        f"help text must mention ATDD_WORKER_READY_TIMEOUT and its default '30'; "
        f"has_env_var={has_env_var}, has_default={has_default}"
    )
