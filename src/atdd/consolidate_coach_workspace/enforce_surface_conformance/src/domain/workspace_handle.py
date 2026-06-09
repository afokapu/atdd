"""Pure cmux workspace-handle sanitizer (issue #1025; relates #601/#865).

``cmux list-workspaces`` decorates each line with a current-workspace marker
(``* ``), a trailing workspace title, and a ``[selected]`` suffix, e.g.
``* workspace:1  ATDD COACH  [selected]``. Feeding that decorated string into a
``cmux list-panes --workspace <handle>`` call makes cmux reject it with
``Invalid workspace handle``. This module extracts the bare ``workspace:N`` token
so a decorated listing line can never reach a workspace-scoped cmux call.

Pure: no I/O, mirrors the ``workspace:\\d+`` extraction already used in
``daemon_manager`` and ``multiplexer._surface_workspace``.
"""
from __future__ import annotations

import re

_WORKSPACE_HANDLE_RE = re.compile(r"workspace:\d+")


def sanitize_workspace_handle(line: str) -> str:
    """Return the bare ``workspace:N`` token from a (possibly decorated) line.

    Raises ``ValueError`` when the line carries no workspace handle at all, so a
    malformed listing line surfaces loudly instead of silently flowing a bad
    handle into a cmux call.
    """
    match = _WORKSPACE_HANDLE_RE.search(line)
    if match is None:
        raise ValueError(f"no workspace handle in cmux listing line: {line!r}")
    return match.group(0)


__all__ = ["sanitize_workspace_handle"]
