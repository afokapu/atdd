# URN: test:dispatch-ux-defaults-and-primer:multiplexer-primer:E005-UNIT-004-primer-not-reprinted-in-same-session
# Acceptance: acc:dispatch-ux-defaults-and-primer:E005-UNIT-004-primer-not-reprinted-in-same-session
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E005
# Phase: RED
# Layer: application
# Runtime: python
"""E005-UNIT-004 — should_print returns False when marker file already exists (second dispatch).

RED: MultiplexerPrimer does not exist, so the idempotency guard is also absent.
The second dispatch in the same session would reprint the primer (if it existed),
cluttering the output after the first dispatch already wrote the marker.
"""
from __future__ import annotations

import io

import pytest

pytestmark = [pytest.mark.platform]


def test_should_print_false_after_first_print(tmp_path):
    """should_print returns False on the second call after print_primer wrote the marker."""
    try:
        from atdd.coach.utils.multiplexer_primer import MultiplexerPrimer
    except ImportError:
        pytest.fail(
            "atdd.coach.utils.multiplexer_primer.MultiplexerPrimer does not exist — "
            "idempotency guard is missing (RED)"
        )

    primer = MultiplexerPrimer()
    env = {"CMUX_WORKSPACE_ID": "workspace:1"}

    # First dispatch: should_print returns True and print_primer creates marker.
    assert primer.should_print(env=env, marker_dir=tmp_path) is True, (
        "should_print must return True on first call (no marker yet)"
    )
    primer.print_primer(backend="cmux", out=io.StringIO(), marker_dir=tmp_path)

    # Second dispatch: should_print must return False (marker now exists).
    result = primer.should_print(env=env, marker_dir=tmp_path)
    assert result is False, (
        f"should_print must return False after marker is created; got {result!r}"
    )


def test_print_primer_not_called_when_should_print_false(tmp_path):
    """When should_print returns False, print_primer should not be called."""
    try:
        from atdd.coach.utils.multiplexer_primer import MultiplexerPrimer
    except ImportError:
        pytest.fail(
            "atdd.coach.utils.multiplexer_primer.MultiplexerPrimer does not exist (RED)"
        )

    primer = MultiplexerPrimer()
    env = {"CMUX_WORKSPACE_ID": "workspace:1"}

    # Pre-create the marker to simulate a previous session dispatch.
    marker_name = getattr(primer, "MARKER_NAME", "primer_shown")
    (tmp_path / marker_name).touch()

    assert primer.should_print(env=env, marker_dir=tmp_path) is False, (
        "should_print must return False when marker exists (pre-condition)"
    )

    # Caller is responsible for checking should_print before calling print_primer;
    # this test verifies that the flag contract holds so callers can rely on it.
    out = io.StringIO()
    # Only call print_primer if should_print is True — this is the guard pattern.
    if primer.should_print(env=env, marker_dir=tmp_path):
        primer.print_primer(backend="cmux", out=out, marker_dir=tmp_path)

    assert out.getvalue() == "", (
        "print_primer must not be called when should_print returns False; "
        f"output was: {out.getvalue()!r}"
    )
