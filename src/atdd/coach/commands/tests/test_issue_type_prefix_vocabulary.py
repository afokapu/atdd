"""#1948 — the issue-type vocabulary has one source, and no type reaches a default.

Three vocabularies claimed to describe issue types and only one was enforced:
``issue.schema.json``'s ``type.enum`` (checked by ``validate_issue_body``).
``TYPE_TO_PREFIX`` disagreed with it on five of seven values and resolved the gap
with ``.get(issue_type, "feat")``, so a ``bug``, ``docs``, ``chore`` or ``devops``
issue silently received a ``feat/`` branch — and three of the six declared
``ALLOWED_BRANCH_PREFIXES`` were unreachable through the map entirely.

Observed on the corpus at filing time (120 most recent issues, all parsed):
``bug`` carried ``fix/`` 24 times and ``feat/`` 21 times; ``refactor`` carried
``feat/`` 9 times against ``refactor/`` 6; one issue carried ``TBD/``, which is
not an allowed prefix at all. The map was already advisory in practice.

These tests pin the decision recorded on #1948: the map is authoritative as a
DEFAULT (so the affordance of ``atdd worktree create <N>`` survives), an unmapped
type RAISES rather than defaulting, and an explicitly supplied branch must still
carry an allowed prefix.
"""
from __future__ import annotations

import pytest


def test_prefix_map_covers_exactly_the_enforced_type_enum():
    """The map and the schema enum are one vocabulary, not two."""
    from atdd.coach.commands.issue_prefixes import TYPE_TO_PREFIX
    from atdd.planner.commands.author_issue import issue_type_enum

    assert set(TYPE_TO_PREFIX) == set(issue_type_enum()), (
        "TYPE_TO_PREFIX and issue.schema.json's type enum have forked. Every "
        "authorable type must map explicitly; a type outside the enum cannot be "
        "authored and has no business carrying a prefix."
    )


@pytest.mark.parametrize("issue_type,expected", [
    ("implementation", "feat"),
    ("feature", "feat"),
    ("bug", "fix"),
    ("refactor", "refactor"),
    ("docs", "docs"),
    ("chore", "chore"),
    ("devops", "devops"),
])
def test_every_authorable_type_maps_to_its_natural_prefix(issue_type, expected):
    """No type reaches the old silent ``feat`` fallback."""
    from atdd.coach.commands.issue_prefixes import prefix_for

    assert prefix_for(issue_type) == expected


def test_unmapped_type_raises_instead_of_defaulting_to_feat():
    """A type with no mapping is an authoring bug; defaulting hid it."""
    from atdd.coach.commands.issue_prefixes import UnknownIssueType, prefix_for

    with pytest.raises(UnknownIssueType) as excinfo:
        prefix_for("analysis")
    assert "analysis" in str(excinfo.value)


def test_every_allowed_prefix_is_reachable_through_the_map():
    """`fix/`, `docs/` and `devops/` were declared allowed and unreachable."""
    from atdd.coach.commands.issue_prefixes import (
        ALLOWED_BRANCH_PREFIXES, TYPE_TO_PREFIX,
    )

    unreachable = set(ALLOWED_BRANCH_PREFIXES) - set(TYPE_TO_PREFIX.values())
    assert not unreachable, (
        f"prefixes declared allowed but not producible by any type: {sorted(unreachable)}"
    )


@pytest.mark.parametrize("branch", ["TBD/something", "wip/experiment", "spike/probe"])
def test_explicit_branch_with_disallowed_prefix_is_refused(branch):
    """An explicit --branch bypassed the prefix check; `TBD/` reached the corpus."""
    from atdd.coach.commands.issue_prefixes import (
        DisallowedBranchPrefix, assert_branch_prefix_allowed,
    )

    with pytest.raises(DisallowedBranchPrefix):
        assert_branch_prefix_allowed(branch)


@pytest.mark.parametrize("branch", [
    "fix/evidence-prefix", "chore/retire-dead-vocabularies", "feat/x", "docs/y", "devops/z",
])
def test_explicit_branch_with_allowed_prefix_is_accepted(branch):
    from atdd.coach.commands.issue_prefixes import assert_branch_prefix_allowed

    assert_branch_prefix_allowed(branch)  # must not raise
