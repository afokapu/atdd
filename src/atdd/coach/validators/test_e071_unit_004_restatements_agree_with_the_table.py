# URN: test:govern-lifecycle:enforce-smoke-refactor-phase-substrate:E071-UNIT-004-restatements-agree-with-the-table
# Acceptance: acc:govern-lifecycle:E071-UNIT-004-restatements-agree-with-the-table
# WMBT: wmbt:govern-lifecycle:E071
# Phase: GREEN
# Layer: unit
# Assertion: structural
"""E071-UNIT-004 — every restatement of merge eligibility is checked against the table.

E071-UNIT-003 removes the *machine's* second copy. This one covers the copies a
machine cannot remove: prose. Four places tell an operator which phases a merge
may auto-close from —

  1. ``pr.convention.yaml`` rule ``description`` (the string CI prints on failure)
  2. that rule's ``fix_hint``
  3. the extracted node ``coach.lifecycle.no-terminal-before-lifecycle-satisfied``
  4. the owning feature's ``description``

— and before this issue, (1) said REFACTOR/COMPLETE while the table said SMOKE
was fine too. Nothing compared them, so the disagreement survived from 3.50.0
until a PR merged through the gap.

The comparison has two legs, and both are needed:

* **positive** — each restatement must carry the phrase rendered *from* the
  table, verbatim. Widen or narrow ``merge_allowed`` and every restatement that
  did not follow fails on the next run. This is precisely the check that was
  missing: with the old table the rendered phrase was "atdd:SMOKE, atdd:REFACTOR
  or atdd:COMPLETE", which appeared in none of the four.
* **negative** — no restatement may name a merge-blocked phase inside a sentence
  that grants merge permission. The positive leg alone would pass prose that
  states the right set and then, two sentences later, tells the reader SMOKE and
  REFACTOR are "the legal exit phases for merge" — which is what the fix_hint
  actually said.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set

import pytest
import yaml

import atdd
from atdd.coach.utils import pr_merge_eligibility as elig
from atdd.coach.utils.repo import find_repo_root

# The restatements all live in the toolkit's own tree (src/atdd/, plan/), which no
# consumer checkout has — module-wide platform marker, per
# coach.source-layout.platform-marker-on-toolkit-selftest.
pytestmark = [pytest.mark.coach, pytest.mark.platform]

# Conventions resolve package-relatively — `src/atdd/` is gone once atdd is
# installed (coach.code-roots.no-hardcoded-toolkit-root). The feature is plan/
# content, which genuinely lives in the repo and never ships; that is one reason
# this module is platform-marked.
_CONVENTIONS = Path(atdd.__file__).resolve().parent / "coach" / "conventions"
_CONVENTION = _CONVENTIONS / "pr.convention.yaml"
_NODE = (
    _CONVENTIONS
    / "nodes"
    / "coach.lifecycle.no-terminal-before-lifecycle-satisfied.convention.yaml"
)
_FEATURE = find_repo_root() / (
    "plan/govern_lifecycle/features/enforce_smoke_refactor_phase_substrate.yaml"
)

_RULE_ID = "coach.pr.merge-blocks-on-pre-smoke-close"

#: Wording that turns a sentence into a claim about which phases MAY merge.
#: Deliberately small and explicit: a marker list is itself hand-maintained, so
#: it earns its keep only by staying short enough to read.
_PERMISSION_MARKERS = (
    "merge-eligible",
    "merge eligible",
    "may merge",
    "may auto-close",
    "legal exit",
    "eligible for merge",
    "allowed to merge",
    "phase label is",
)

_PHASE_TOKEN = re.compile(r"atdd:([A-Z_]+)")


def _load(path) -> dict:
    assert path.is_file(), f"restatement source missing: {path}"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _rule() -> dict:
    for rule in _load(_CONVENTION).get("rules") or []:
        if rule.get("id") == _RULE_ID:
            return rule
    pytest.fail(f"{_RULE_ID} is not declared in {_CONVENTION}")


def restatements() -> Dict[str, str]:
    """Every human-facing statement of which phases may carry an auto-closing PR."""
    rule = _rule()
    node = _load(_NODE)
    return {
        "pr.convention.yaml::rules[].description": str(rule.get("description") or ""),
        "pr.convention.yaml::rules[].fix_hint": str(rule.get("fix_hint") or ""),
        "nodes/coach.lifecycle.no-terminal-before-lifecycle-satisfied::content.fix_hint": str(
            (node.get("content") or {}).get("fix_hint") or ""
        ),
        "features/enforce_smoke_refactor_phase_substrate.yaml::description": str(
            _load(_FEATURE).get("description") or ""
        ),
    }


def _sentences(text: str) -> List[str]:
    return [s for s in re.split(r"(?<=[.;:])\s+|\n{2,}", text) if s.strip()]


@pytest.mark.parametrize("source", sorted(restatements()))
def test_restatement_carries_the_phrase_rendered_from_the_table(source: str) -> None:
    """The positive leg: the table's own rendering must appear verbatim."""
    phrase = elig.render_allowed_phrase()
    text = restatements()[source]

    assert text, f"{source} is empty — a restatement that says nothing cannot be checked"
    assert phrase in text, (
        f"{source} does not name the merge-eligible phases the table declares.\n"
        f"  phase_labels.merge_allowed renders as: {phrase!r}\n"
        "Update the prose, or the table, until the two say one thing. This is the "
        "comparison whose absence let the description and the table disagree from "
        "3.50.0 until #1710."
    )


@pytest.mark.parametrize("source", sorted(restatements()))
def test_restatement_never_grants_merge_permission_to_a_blocked_phase(
    source: str,
) -> None:
    """The negative leg: no permission-granting sentence may name a blocked phase."""
    allowed: Set[str] = set(elig.merge_allowed_phases())
    text = restatements()[source]

    offenders: List[str] = []
    for sentence in _sentences(text):
        lowered = sentence.lower()
        if not any(marker in lowered for marker in _PERMISSION_MARKERS):
            continue
        named = set(_PHASE_TOKEN.findall(sentence))
        wrong = named - allowed
        if wrong:
            offenders.append(f"{sorted(wrong)} in: {sentence.strip()!r}")

    assert not offenders, (
        f"{source} tells an operator a merge-blocked phase may carry an auto-close.\n"
        + "\n".join(f"  - {o}" for o in offenders)
        + f"\nMerge-eligible phases are {sorted(allowed)}."
    )


def test_at_least_one_restatement_states_the_set_positively() -> None:
    """Guard against a vacuous pass: the checks above must have something to bite on."""
    allowed = set(elig.merge_allowed_phases())
    for text in restatements().values():
        for sentence in _sentences(text):
            if any(m in sentence.lower() for m in _PERMISSION_MARKERS):
                if set(_PHASE_TOKEN.findall(sentence)) == allowed:
                    return
    pytest.fail(
        "no restatement contains a permission sentence naming exactly "
        f"{sorted(allowed)} — the negative leg is scanning nothing, so it would "
        "pass on prose that says anything at all"
    )
