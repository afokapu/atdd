# URN: test:dispatch-ux-defaults-and-primer:multiplexer-primer:E005-UNIT-001-primer-printed-when-mux-detected
# Acceptance: acc:dispatch-ux-defaults-and-primer:E005-UNIT-001-primer-printed-when-mux-detected
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E005
# Phase: RED
# Layer: application
# Runtime: python
"""E005-UNIT-001 — MultiplexerPrimer.should_print returns True when CMUX_WORKSPACE_ID set and marker absent.

RED: MultiplexerPrimer does not exist in src/atdd/coach/utils/multiplexer_primer.py.
Operators spend ~5 minutes per session discovering cmux commands that should be
printed automatically on first dispatch.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def test_should_print_true_when_cmux_set_and_no_marker(tmp_path):
    """should_print returns True when CMUX_WORKSPACE_ID is set and marker file absent."""
    try:
        from atdd.coach.utils.multiplexer_primer import MultiplexerPrimer
    except ImportError:
        pytest.fail(
            "atdd.coach.utils.multiplexer_primer.MultiplexerPrimer does not exist — "
            "multiplexer primer module is missing (RED)"
        )

    primer = MultiplexerPrimer()
    result = primer.should_print(
        env={"CMUX_WORKSPACE_ID": "workspace:1"},
        marker_dir=tmp_path,
    )
    assert result is True, (
        f"should_print must return True when CMUX_WORKSPACE_ID set and no marker; "
        f"got {result!r}"
    )


def test_should_print_false_when_marker_exists(tmp_path):
    """should_print returns False when the primer marker file already exists."""
    try:
        from atdd.coach.utils.multiplexer_primer import MultiplexerPrimer
    except ImportError:
        pytest.fail(
            "atdd.coach.utils.multiplexer_primer.MultiplexerPrimer does not exist (RED)"
        )

    # Create the marker file that should suppress the primer.
    primer = MultiplexerPrimer()
    marker_name = getattr(primer, "MARKER_NAME", "primer_shown")
    (tmp_path / marker_name).touch()

    result = primer.should_print(
        env={"CMUX_WORKSPACE_ID": "workspace:1"},
        marker_dir=tmp_path,
    )
    assert result is False, (
        f"should_print must return False when marker file exists; got {result!r}"
    )


def test_should_print_false_when_no_mux_env(tmp_path):
    """should_print returns False when no multiplexer env var is set."""
    try:
        from atdd.coach.utils.multiplexer_primer import MultiplexerPrimer
    except ImportError:
        pytest.fail(
            "atdd.coach.utils.multiplexer_primer.MultiplexerPrimer does not exist (RED)"
        )

    primer = MultiplexerPrimer()
    result = primer.should_print(env={}, marker_dir=tmp_path)
    assert result is False, (
        f"should_print must return False when no mux env var is set; got {result!r}"
    )
