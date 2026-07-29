# URN: test:govern-lifecycle:bind-issue-feature:L003-INTEGRATION-001-no-atdd-wmbt-label-dependency-remains
# Acceptance: acc:govern-lifecycle:L003-INTEGRATION-001-no-atdd-wmbt-label-dependency-remains
# WMBT: wmbt:govern-lifecycle:L003
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: No coach code path reaches the atdd-wmbt label for WMBT resolution, and the retired mint path stays retired.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:L003-INTEGRATION-001-no-atdd-wmbt-label-dependency-remains
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:L003

Purpose: the decommissioned lookup must be gone, not merely bypassed.

Two ways this regresses. It can be left in place beside the new resolver, so a
fallback path silently reinstates the empty answer; or the fix can drift back
toward re-minting GitHub sub-issues, which #1477 removed and
test_mint_path_decommissioned.py asserts stays gone (Decision #4 on #1635).

Fails today because `_fetch_sub_issues` still carries the label search.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from ._bind_issue_feature_helpers import source_of

pytestmark = [pytest.mark.platform]

_COACH = Path(__file__).resolve().parents[2]  # src/atdd/coach
_LABEL = re.compile(r"atdd-wmbt")

# The retired mint-path symbols. Decision #4: do not revive them.
_RETIRED = ("sync_wmbts", "_discover_wmbts_from_feature")

_PRUNE = {"__pycache__", "tests", "validators"}


def _coach_sources():
    for path in sorted(_COACH.rglob("*.py")):
        if any(part in _PRUNE for part in path.parts):
            continue
        yield path


def test_no_coach_path_resolves_wmbts_through_the_atdd_wmbt_label() -> None:
    """The label search must be gone from the shipped coach tree."""
    offenders = [
        str(p.relative_to(_COACH.parents[2]))
        for p in _coach_sources()
        if _LABEL.search(p.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == [], (
        "coach code still references the atdd-wmbt label for WMBT resolution: "
        + ", ".join(offenders)
        + ". Nothing has minted that label since #1477; the newest such issue "
        "is #1059 and the 56 that exist are all pre-#1477 leftovers."
    )


def test_the_retired_mint_path_stays_retired() -> None:
    """Repointing at plan/ must not resurrect sync_wmbts (Decision #4)."""
    revived = []
    for path in _coach_sources():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _RETIRED:
                revived.append(f"{path.name}::{node.name}")
    assert revived == [], (
        "the #1477-retired mint path was revived: " + ", ".join(revived)
        + ". test_mint_path_decommissioned.py asserts these stay gone."
    )


def test_the_fetch_sub_issues_seam_no_longer_queries_a_provider() -> None:
    """The specific function named in the #1635 root cause."""
    source = source_of("atdd.coach.commands.issue_lifecycle")
    assert "atdd-wmbt" not in source, (
        "issue_lifecycle.py still carries the atdd-wmbt label search that made "
        "`atdd coach enter <N>` print 'WMBTs: none found' for every issue"
    )


def test_the_plan_backed_resolver_is_what_the_lifecycle_calls() -> None:
    """A new resolver that nothing calls would leave the symptom in place."""
    source = source_of("atdd.coach.commands.issue_lifecycle")
    assert "resolve_wmbts_for_issue" in source, (
        "issue_lifecycle.py does not call the plan-backed resolver, so the "
        "coach surface would keep showing the old answer"
    )
