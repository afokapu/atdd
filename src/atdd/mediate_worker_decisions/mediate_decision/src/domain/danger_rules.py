"""Pure danger-action pattern matcher (no I/O).

The list is intentionally conservative and substring-based: anything that could
irreversibly mutate shared state must escalate to a human. Used by the safety
gate BEFORE the coach is ever consulted (WMBT C002).
"""
from __future__ import annotations

from typing import Optional

DANGER_PATTERNS = (
    "git push",
    "force push",
    "git push --force",
    "git merge",
    "gh pr merge",
    "rm -rf",
    "drop table",
    "destructive migration",
    "force-push",
)


def match_danger(text: str) -> Optional[str]:
    """Return the first danger pattern found in ``text`` (case-insensitive), or None."""
    if not text:
        return None
    low = text.lower()
    for pattern in DANGER_PATTERNS:
        if pattern in low:
            return pattern
    return None
