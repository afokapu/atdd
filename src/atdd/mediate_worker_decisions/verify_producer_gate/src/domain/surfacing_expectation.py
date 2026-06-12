"""SurfacingExpectation — the pure freedom-layer partition (WMBT C010).

STUB (RED #1076): the contract surface only. GREEN implements
``classify_command`` so it reads the post-#1062 scoped Bash allow-list
(``session.convention.yaml::spawn_time.freedom_layer`` — the comma-delimited
``Bash(<pattern>)`` patterns, #1062 E031/E032) and partitions a command into
expected-auto-run (pre-authorized, no Feed item) vs expected-surfaced (gated,
publishes a ``permissionRequest``). The partition is DERIVED from the allow-list
passed in, never a hardcoded second copy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# Surfacing kinds the gate distinguishes.
KIND_AUTO_RUN = "auto-run"
KIND_PERMISSION_REQUEST = "permissionRequest"


@dataclass(frozen=True)
class SurfacingExpectation:
    """Whether a command is expected to surface to the Feed, and as what kind."""

    command: str
    surfaces: bool
    kind: str


def classify_command(
    command: str, *, bash_allow: Sequence[str]
) -> SurfacingExpectation:
    """Classify ``command`` against the freedom-layer scoped Bash allow-list.

    A command matching one of ``bash_allow`` (e.g. ``"pytest:*"`` — a prefix wildcard
    mirroring Claude Code's ``Bash(pytest:*)`` scoped-allow syntax) is
    expected-auto-run (``surfaces=False``); otherwise it is expected-surfaced as a
    ``permissionRequest`` (``surfaces=True``). The partition is derived from
    ``bash_allow`` — no command is hardcoded.
    """
    cmd = command.strip()
    for pattern in bash_allow:
        prefix = pattern[:-2].strip() if pattern.endswith(":*") else pattern.strip()
        if prefix and (cmd == prefix or cmd.startswith(prefix + " ")):
            return SurfacingExpectation(
                command=command, surfaces=False, kind=KIND_AUTO_RUN
            )
    return SurfacingExpectation(
        command=command, surfaces=True, kind=KIND_PERMISSION_REQUEST
    )
