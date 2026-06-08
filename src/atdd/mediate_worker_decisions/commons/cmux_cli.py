"""Shared cmux CLI access (wagon-internal commons).

One place for "run a cmux subcommand" and "strip ANSI", so the integration
adapters (surface reader, coach client, send applier) don't each re-implement
the subprocess call and the escape-stripping regex. cmux surface refs are
workspace-scoped, so callers always pass ``--workspace``.
"""
from __future__ import annotations

import logging
import re
import subprocess

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

_log = logging.getLogger("atdd.mediate_worker_decisions.cmux_cli")


class CmuxCommandError(RuntimeError):
    """A ``cmux`` subcommand exited non-zero (e.g. a broken-pipe rpc failure).

    Carries the argv/returncode/stderr so a failed cmux call is SURFACED rather
    than swallowed into ``""`` — the #1007 observability bug where a detached
    daemon's broken-pipe ``cmux rpc`` masqueraded as an empty Feed.
    """

    def __init__(self, argv: list[str], returncode: int, stderr: str) -> None:
        self.argv = list(argv)
        self.returncode = returncode
        self.stderr = stderr or ""
        super().__init__(
            f"cmux {' '.join(argv)!r} exited {returncode}: {self.stderr.strip()}"
        )


def run_cmux(*args: str, timeout: float = 15.0) -> str:
    """Run ``cmux <args>`` and return stdout (empty string on no output).

    A non-zero cmux exit is SURFACED — loud-logged and raised as
    ``CmuxCommandError`` — never swallowed into ``""``. The #1007 reopen: a
    detached daemon's ``cmux rpc`` broke-pipe (``errno 32``) against a stale
    socket and this helper returned ``""``, so the daemon saw an empty Feed every
    poll and silently never decided. Surfacing it makes a broken Feed connection
    visible (in daemon.log) instead of masquerading as an empty Feed.
    """
    result = subprocess.run(
        ["cmux", *args], capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        _log.warning(
            "cmux command failed — surfacing instead of swallowing to empty output",
            extra={
                "argv": ["cmux", *args],
                "returncode": result.returncode,
                "stderr": (result.stderr or "").strip(),
            },
        )
        raise CmuxCommandError(["cmux", *args], result.returncode, result.stderr or "")
    return result.stdout or ""


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")
