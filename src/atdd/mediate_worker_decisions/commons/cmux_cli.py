"""Shared cmux CLI access (wagon-internal commons).

One place for "run a cmux subcommand" and "strip ANSI", so the integration
adapters (surface reader, coach client, send applier) don't each re-implement
the subprocess call and the escape-stripping regex. cmux surface refs are
workspace-scoped, so callers always pass ``--workspace``.
"""
from __future__ import annotations

import re
import subprocess

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def run_cmux(*args: str, timeout: float = 15.0) -> str:
    """Run ``cmux <args>`` and return stdout (empty string on no output)."""
    result = subprocess.run(
        ["cmux", *args], capture_output=True, text=True, timeout=timeout
    )
    return result.stdout or ""


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")
