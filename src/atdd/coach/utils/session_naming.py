# URN: component:govern-lifecycle:enforcement-substrate:session_naming:backend:domain
# Runtime: python
# Purpose: Compute + parse canonical ATDD session names (issue #470).

"""Canonical session-name + layout-policy helpers (issue #470).

Pure functions: compute the canonical ``<REPO><N>[-phase<M>]-<slug>`` name
from issue + branch metadata, parse a name back into its components, and
look up the target grid label for a given surface count.

These helpers are reused by:

    * ``atdd orchestrate``      — dispatch-time naming + layout pass
    * ``atdd session-template`` — inlines the canonical name in the launch prompt
    * ``atdd babysit``          — drift detection + auto-correct on every tick
    * the ``test_orchestration_session_naming`` validator (phase 3)

Single source of truth for the regex is ``orchestration.convention.yaml::
session_naming.regex`` — this module mirrors it with a tested helper but
the convention is authoritative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


# Canonical format regex. Mirrored from orchestration.convention.yaml::
# session_naming.regex; the validator asserts the two stay in sync.
CANONICAL_NAME_REGEX = re.compile(
    r"^([A-Z]{2,8})(\d+)(-phase\d+)?-([a-z0-9]+(?:-[a-z0-9]+)*)$"
)

_BRANCH_PREFIXES: tuple[str, ...] = (
    "feat/",
    "fix/",
    "refactor/",
    "chore/",
    "docs/",
    "devops/",
    "test/",
)


@dataclass(frozen=True)
class ParsedName:
    repo: str
    issue: int
    phase: Optional[int]
    slug: str


def compute_repo_short_name(config: Optional[Dict[str, Any]]) -> str:
    """Resolve the ``<REPO>`` token from ``.atdd/config.yaml``.

    Precedence (Decision row 1 of issue #470):

        1. ``repo.short_name`` if set (uppercased verbatim).
        2. Last hyphen-segment of ``github.repo`` (e.g. ``afokapu/atdd`` →
           ``ATDD``), uppercased.
        3. Fallback ``REPO`` so callers always get a non-empty token.
    """
    if not isinstance(config, dict):
        return "REPO"
    repo_block = config.get("repo")
    if isinstance(repo_block, dict):
        explicit = repo_block.get("short_name")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip().upper()
    github_block = config.get("github") or {}
    repo_field = github_block.get("repo") if isinstance(github_block, dict) else None
    if isinstance(repo_field, str) and repo_field.strip():
        last = repo_field.rsplit("/", 1)[-1].rsplit("-", 1)[-1]
        if last:
            return last.upper()
    return "REPO"


def branch_to_slug(branch: str) -> str:
    """Strip the conventional prefix (feat/, fix/, etc.) from a branch name."""
    if not branch:
        return ""
    for prefix in _BRANCH_PREFIXES:
        if branch.startswith(prefix):
            return branch[len(prefix):]
    if "/" in branch:
        return branch.split("/", 1)[1]
    return branch


def truncate_slug(slug: str, max_len: int = 40) -> str:
    """Truncate a slug at the last hyphen boundary <= max_len.

    Decision row 7: prefer word-boundary truncation over mid-token cuts.
    Returns the original slug when it already fits.
    """
    if len(slug) <= max_len:
        return slug
    head = slug[:max_len]
    cut = head.rfind("-")
    if cut > 0:
        return head[:cut]
    return head


def compute_canonical_name(
    repo: str,
    issue_number: int,
    slug: str,
    phase: Optional[int] = None,
) -> str:
    """Build the canonical session name from its components.

    >>> compute_canonical_name("ATDD", 470, "canonical-session-naming")
    'ATDD470-canonical-session-naming'
    >>> compute_canonical_name("ATDD", 462, "bump-on-merge", phase=2)
    'ATDD462-phase2-bump-on-merge'
    """
    repo_token = (repo or "REPO").upper()
    slug_token = truncate_slug((slug or "session").lower())
    phase_token = f"-phase{phase}" if phase and phase >= 1 else ""
    return f"{repo_token}{issue_number}{phase_token}-{slug_token}"


def parse_canonical_name(name: str) -> Optional[ParsedName]:
    """Parse a session name into ``(repo, issue, phase, slug)`` or None."""
    if not isinstance(name, str):
        return None
    match = CANONICAL_NAME_REGEX.match(name.strip())
    if not match:
        return None
    repo, issue, phase_marker, slug = match.group(1), match.group(2), match.group(3), match.group(4)
    phase = int(phase_marker[len("-phase"):]) if phase_marker else None
    return ParsedName(repo=repo, issue=int(issue), phase=phase, slug=slug)


def is_canonical_name(name: str) -> bool:
    """True when ``name`` matches the canonical regex."""
    return parse_canonical_name(name) is not None


# ---------------------------------------------------------------------------
# Layout policy (issue #470, decisions 8-13)
# ---------------------------------------------------------------------------


def target_grid_label(active_surface_count: int) -> str:
    """Return the human-readable target layout for ``active_surface_count``.

    Mirrors ``orchestration.convention.yaml::layout_placement.policy``;
    the value is purely informational (used by babysit's notice and the
    validator's drift message). No actual cmux ops are issued from this
    helper — placement is the multiplexer backend's responsibility.
    """
    n = max(0, int(active_surface_count))
    if n == 0:
        return "shell-only (left pane)"
    if n == 1:
        return "shell (left) + 1 surface (right)"
    if n == 2:
        return "shell (left) + 2 surfaces stacked vertically (right)"
    if n <= 4:
        return "shell (left) + 2x2 grid (right region)"
    if n <= 6:
        return "shell (left) + 2x3 grid (right region)"
    return "shell (left) + dense column grid (3+ columns x N rows)"


__all__ = [
    "CANONICAL_NAME_REGEX",
    "ParsedName",
    "branch_to_slug",
    "compute_canonical_name",
    "compute_repo_short_name",
    "is_canonical_name",
    "parse_canonical_name",
    "target_grid_label",
    "truncate_slug",
]
