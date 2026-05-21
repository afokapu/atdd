# URN: test:dispatch-ux-defaults-and-primer:multiplexer-primer:E005-UNIT-002-primer-text-contains-key-commands
# Acceptance: acc:dispatch-ux-defaults-and-primer:E005-UNIT-002-primer-text-contains-key-commands
# WMBT: wmbt:dispatch-ux-defaults-and-primer:E005
# Phase: RED
# Layer: application
# Runtime: python
"""E005-UNIT-002 — print_primer writes cmux primer text with 5 key commands and creates marker.

RED: MultiplexerPrimer.print_primer does not exist. The primer text itself has
not been written — operators have no automated way to discover the 5 cmux
commands they invariably need during a dispatch session.
"""
from __future__ import annotations

import io

import pytest

pytestmark = [pytest.mark.platform]

_REQUIRED_CMUX_PATTERNS = [
    "cmux tree",
    "cmux send-key",
    "cmux read-screen",
    "cmux close-surface",
]


def test_print_primer_contains_key_cmux_commands(tmp_path):
    """print_primer writes all 5 key cmux patterns to the output stream."""
    try:
        from atdd.coach.utils.multiplexer_primer import MultiplexerPrimer
    except ImportError:
        pytest.fail(
            "atdd.coach.utils.multiplexer_primer.MultiplexerPrimer does not exist — "
            "primer text is missing (RED)"
        )

    primer = MultiplexerPrimer()
    out = io.StringIO()
    primer.print_primer(backend="cmux", out=out, marker_dir=tmp_path)
    text = out.getvalue()

    for pattern in _REQUIRED_CMUX_PATTERNS:
        assert pattern in text, (
            f"cmux primer must contain {pattern!r} but got: {text!r}"
        )

    assert "paste" in text.lower() or "paste_buffer" in text.lower() or "paste-buffer" in text.lower(), (
        f"cmux primer must mention paste-buffer ergonomics; got: {text!r}"
    )


def test_print_primer_creates_marker_file(tmp_path):
    """print_primer creates the marker file in marker_dir after printing."""
    try:
        from atdd.coach.utils.multiplexer_primer import MultiplexerPrimer
    except ImportError:
        pytest.fail(
            "atdd.coach.utils.multiplexer_primer.MultiplexerPrimer does not exist (RED)"
        )

    primer = MultiplexerPrimer()
    out = io.StringIO()
    primer.print_primer(backend="cmux", out=out, marker_dir=tmp_path)

    marker_files = list(tmp_path.iterdir())
    assert marker_files, (
        f"print_primer must create a marker file in {tmp_path}; directory is empty"
    )
