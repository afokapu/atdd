"""Role value object (pure) — the role segment of a role-aware canonical name.

role ∈ {worker, coach-daemon, observer}. These are the only managed-surface
roles the coach names; an unknown role token is never guessed into a parse.
"""
from __future__ import annotations

WORKER = "worker"
COACH_DAEMON = "coach-daemon"
OBSERVER = "observer"

ROLES: frozenset[str] = frozenset({WORKER, COACH_DAEMON, OBSERVER})


def is_valid_role(role: str) -> bool:
    """True when ``role`` is one of the canonical managed-surface roles."""
    return role in ROLES
