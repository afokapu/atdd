"""Role-aware canonical surface-name builder / sanitizer / parser (pure).

Format ``<REPO><N>[-phase<M>]-<role>-<slug>`` with role ∈ {worker, coach-daemon,
observer}. Reuses the #470 primitive ``session_naming.compute_canonical_name``
(and its slug truncation) for the repo/issue/phase/slug scaffolding so there is a
single source of truth for the base shape; this module only adds the role segment
and the role-aware parser.

issue #865 — RED stubs raise NotImplementedError; GREEN fills them in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.role import (
    ROLES,
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
    raise NotImplementedError("enforce-surface-conformance: sanitize_slug (GREEN)")


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
    raise NotImplementedError(
        "enforce-surface-conformance: build_role_aware_name (GREEN)"
    )


def parse_role_aware_name(name: str) -> Optional[ParsedRoleName]:
    """Parse a role-aware name into its components, or ``None`` if it does not
    match. An unknown role token never parses (the role is never guessed)."""
    raise NotImplementedError(
        "enforce-surface-conformance: parse_role_aware_name (GREEN)"
    )


def is_role_aware_name(name: str) -> bool:
    """True when ``name`` matches the role-aware canonical shape."""
    raise NotImplementedError(
        "enforce-surface-conformance: is_role_aware_name (GREEN)"
    )


__all__ = [
    "ROLE_AWARE_NAME_REGEX",
    "ROLES",
    "ParsedRoleName",
    "build_role_aware_name",
    "is_role_aware_name",
    "parse_role_aware_name",
    "sanitize_slug",
]
