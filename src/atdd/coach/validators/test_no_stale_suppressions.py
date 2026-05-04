# URN: component:govern-lifecycle:enforcement-substrate:no_stale_suppressions:backend:domain
# Runtime: python
# Purpose: Fail CI when any ``# atdd:suppress(<id>) UNTIL=<date>`` marker is past its deadline.

"""
Coach validator: stale-suppression detector (issue #395).

Walks the consumer repo (``python/``, ``web/src/``, ``supabase/``,
``packages/``) and the toolkit (``src/atdd/``) for inline pragmas of the
form::

    # atdd:suppress(<RULE_ID>) UNTIL=YYYY-MM-DD     (Python)
    // atdd:suppress(<RULE_ID>) UNTIL=YYYY-MM-DD    (TypeScript / TSX)

A marker is *stale* when its ``UNTIL=`` date is past today. Per Decision 4
(issue #395), markers without an ``UNTIL=`` segment are NOT stale — the
deadline is optional in v1, and strict orgs may layer on a separate
disposition rule to require it.

Rule emitted: ``coach.rule-id.stale-suppression``.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.suppression_scanner import (
    SuppressionMarker,
    find_stale_suppressions,
)


pytestmark = [pytest.mark.coach, pytest.mark.platform]


_RULE_ID = "coach.rule-id.stale-suppression"


def _scan_roots() -> List[Path]:
    """Roots that may carry suppression markers."""
    repo = find_repo_root()
    candidates = [
        repo / "python",
        repo / "web" / "src",
        repo / "supabase",
        repo / "packages",
        repo / "e2e",
        Path(atdd.__file__).resolve().parent,  # toolkit dogfooding
    ]
    return [p for p in candidates if p.is_dir()]


def _format_stale(stale: List[SuppressionMarker]) -> str:
    repo = find_repo_root()
    lines = [
        f"[ERROR] {_RULE_ID}: {len(stale)} stale suppression marker(s):"
    ]
    for marker in sorted(stale, key=lambda m: (str(m.file_path), m.line)):
        try:
            rel = marker.file_path.resolve().relative_to(repo.resolve())
        except ValueError:
            rel = marker.file_path
        lines.append(
            f"  {rel}:{marker.line}   {marker.rule_id}   "
            f"UNTIL={marker.until.isoformat()} (past)"
        )
    lines.append("")
    lines.append("  Either fix the underlying violation or extend UNTIL=.")
    return "\n".join(lines)


@pytest.mark.coach
def test_no_stale_suppressions():
    """Fail CI when an inline suppression marker has expired.

    Issue #395: replaces the count-based ratchet with deadline-bounded
    suppressions. Reviewers see an inventory of ``# atdd:suppress(...)``
    sites at any moment, and CI surfaces ones whose deadline has lapsed.
    """
    stale = find_stale_suppressions(_scan_roots())
    if not stale:
        return
    pytest.fail(_format_stale(stale))
