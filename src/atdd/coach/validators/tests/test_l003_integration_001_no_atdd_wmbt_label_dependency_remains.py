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

# Label ADMINISTRATION is not label-based RESOLUTION, and #1635 puts the former
# explicitly out of scope ("Retiring the 56 legacy atdd-wmbt GitHub issues …
# is a separate cleanup"). These two mention the label for reasons that have
# nothing to do with finding an issue's WMBTs:
#
#   sync_labels.py  — an argparse `help=` string describing which issues the
#                     verb re-derives labels for.
#   initializer.py  — emits a generated GitHub *workflow* label filter
#                     (`contains(github.event.issue.labels.*.name, …)`) when
#                     scaffolding a repo, and declares the label set `atdd init`
#                     creates.
#
# Banning the token here too would force this issue to absorb a cleanup it
# declared out of scope. What must hold is that nothing RESOLVES WMBTs through
# the label — which is what the rest of this file asserts.
_LABEL_ADMIN_ALLOWED = {
    "coach_verbs/sync_labels.py",
    "initializer.py",
}


def _is_label_admin(path: Path) -> bool:
    rel = str(path.relative_to(_COACH / "commands")) if _COACH / "commands" in path.parents else path.name
    return rel in _LABEL_ADMIN_ALLOWED or path.name in _LABEL_ADMIN_ALLOWED


def _coach_sources():
    for path in sorted(_COACH.rglob("*.py")):
        if any(part in _PRUNE for part in path.parts):
            continue
        yield path


def _docstring_constants(tree: ast.Module) -> set:
    """id() of every node that is a module/class/function docstring."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                ids.add(id(body[0].value))
    return ids


def _runtime_string_literals(source: str):
    """String constants that are real runtime values, not prose.

    A *usage* of the retired label is a string literal handed to a subprocess.
    Prose *documenting* its removal is a docstring or a comment. A raw text scan
    cannot tell them apart, and would make the change unexplainable in the very
    file that made it — a worse outcome than the risk it guards. What must hold
    is that no code PASSES the label, not that the token is unmentionable.
    """
    tree = ast.parse(source)
    skip = _docstring_constants(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in skip:
                yield node.value


def test_no_coach_path_resolves_wmbts_through_the_atdd_wmbt_label() -> None:
    """The label search must be gone from the shipped coach tree."""
    offenders = []
    for path in _coach_sources():
        if _is_label_admin(path):
            continue
        try:
            literals = list(_runtime_string_literals(
                path.read_text(encoding="utf-8", errors="ignore")))
        except SyntaxError:
            continue
        if any(_LABEL.search(text) for text in literals):
            offenders.append(str(path.relative_to(_COACH.parents[2])))

    assert offenders == [], (
        "coach code still passes the retired WMBT label as a runtime value: "
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
    literals = list(_runtime_string_literals(
        source_of("atdd.coach.commands.issue_lifecycle")))
    assert not [t for t in literals if _LABEL.search(t)], (
        "issue_lifecycle.py still passes the retired WMBT label to a provider — "
        "the search that made `atdd coach enter <N>` print 'WMBTs: none found' "
        "for every issue in the repo"
    )


def test_the_plan_backed_resolver_is_what_the_lifecycle_calls() -> None:
    """A new resolver that nothing calls would leave the symptom in place."""
    source = source_of("atdd.coach.commands.issue_lifecycle")
    assert "resolve_wmbts_for_issue" in source, (
        "issue_lifecycle.py does not call the plan-backed resolver, so the "
        "coach surface would keep showing the old answer"
    )
