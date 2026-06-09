"""Role-aware canonical surface-name builder / sanitizer / parser (pure).

Format ``<REPO><N>[-phase<M>]-<role>-<slug>`` with role ∈ {worker, coach-daemon,
observer}. Reuses the #470 primitive ``session_naming.compute_canonical_name``
(and its slug truncation) for the repo/issue/phase/slug scaffolding so there is a
single source of truth for the base shape; this module only adds the role segment
and the role-aware parser (issue #865).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from atdd.coach.utils.session_naming import compute_canonical_name, truncate_slug
from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.role import (
    ROLES,
    is_valid_role,
)

# Role-aware canonical name regex (role alternation between the optional phase
# infix and the slug). Mirrors contracts/commons/coach/canonical-surface-name.schema.json.
ROLE_AWARE_NAME_REGEX = re.compile(
    r"^([A-Z]{2,8})(\d+)(-phase\d+)?-(worker|coach-daemon|observer)-"
    r"([a-z0-9]+(?:-[a-z0-9]+)*)$"
)


@dataclass(frozen=True)
class ParsedRoleName:
    repo: str
    issue: int
    phase: Optional[int]
    role: str
    slug: str


def sanitize_slug(slug: str) -> str:
    """Lowercase, restrict to ``[a-z0-9-]``, collapse repeats, truncate <= 40.

    Reuses ``session_naming.truncate_slug`` for the word-boundary truncation
    (#470 decision 7).
    """
    lowered = (slug or "").lower()
    # Any run of non-[a-z0-9] becomes a single hyphen; strip the ends.
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return truncate_slug(hyphenated)


def build_role_aware_name(
    repo: str,
    issue: int,
    role: str,
    slug: str,
    phase: Optional[int] = None,
) -> str:
    """Build ``<REPO><N>[-phase<M>]-<role>-<slug>``.

    Reuses ``session_naming.compute_canonical_name`` by feeding it a combined
    ``<role>-<sanitized-slug>`` slug; raises ``ValueError`` on an invalid role.
    """
    if not is_valid_role(role):
        raise ValueError(
            f"invalid role {role!r}; must be one of {sorted(ROLES)}"
        )
    combined = f"{role}-{sanitize_slug(slug)}"
    return compute_canonical_name(repo, issue, combined, phase=phase)


def parse_role_aware_name(name: str) -> Optional[ParsedRoleName]:
    """Parse a role-aware name into its components, or ``None`` if it does not
    match. An unknown role token never parses (the role is never guessed)."""
    if not isinstance(name, str):
        return None
    match = ROLE_AWARE_NAME_REGEX.match(name.strip())
    if not match:
        return None
    repo, issue, phase_marker, role, slug = match.groups()
    phase = int(phase_marker[len("-phase"):]) if phase_marker else None
    return ParsedRoleName(
        repo=repo, issue=int(issue), phase=phase, role=role, slug=slug
    )


def is_role_aware_name(name: str) -> bool:
    """True when ``name`` matches the role-aware canonical shape."""
    return parse_role_aware_name(name) is not None


__all__ = [
    "ROLE_AWARE_NAME_REGEX",
    "ROLES",
    "ParsedRoleName",
    "build_role_aware_name",
    "is_role_aware_name",
    "parse_role_aware_name",
    "sanitize_slug",
]
