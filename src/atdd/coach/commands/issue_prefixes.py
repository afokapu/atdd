"""Neutral home for the issue-type → commit/branch prefix constants.

EXTRACTED from ``issue.py`` (the ``atdd issue`` monolith) by C5a (#1382, umbrella
#1303) so ``branch.py`` / ``pr.py`` — and any other consumer — stop hard-depending
on the monolith for these two constants. ``issue.py`` re-exports them unchanged
(single source of truth stays here), so nothing breaks now and C5b (#1309) can
delete the ``atdd issue`` subparser + monolith without taking the prefixes with it.

#1948 — ONE VOCABULARY, NO DEFAULT. This map was extracted verbatim from the
monolith and never reconciled with ``issue.schema.json``'s ``type.enum``, which is
the vocabulary the authoring validator actually enforces. The two forked: the map
carried five types that cannot be authored at all (``analysis``, ``planning``,
``cleanup``, ``migration``, ``tracking``) while four types that CAN be authored
(``bug``, ``docs``, ``chore``, ``devops``) had no entry and fell through a
``.get(issue_type, "feat")`` default. The consequences were not theoretical:

* ``fix/``, ``docs/`` and ``devops/`` were declared in
  :data:`ALLOWED_BRANCH_PREFIXES` and were *unreachable* through the map, so no
  issue type could ever produce them;
* across the 120 most recent issues, ``bug`` carried ``fix/`` 24 times and
  ``feat/`` 21 times — the same declared type, two prefixes, depending only on
  whether a human passed ``--branch``;
* one issue reached the corpus carrying ``TBD/``, which is not an allowed prefix.

The map is now AUTHORITATIVE AS A DEFAULT and covers exactly the enforced enum.
Resolution goes through :func:`prefix_for`, which RAISES on an unmapped type
rather than defaulting: a type with no mapping is an authoring bug, and the
silent ``feat`` fallback is precisely what hid it. An explicit ``--branch``
remains legal — deliberately, since the corpus shows deliberate overrides — but
must carry an allowed prefix, which is what :func:`assert_branch_prefix_allowed`
checks and what the ``TBD/`` branch would have failed.

The map's KEYS are drift-checked against ``issue.schema.json`` by
``test_issue_type_prefix_vocabulary.py``; do not add a key here without adding it
to the schema enum, and do not remove one from the schema without removing it
here.
"""
from __future__ import annotations

# Issue type → conventional commit / branch prefix mapping.
# KEYS MUST EQUAL `issue.schema.json`'s `type.enum` (drift-tested). Used by
# `atdd author issue` (title + Branch row) and `atdd worktree create` (prefix).
TYPE_TO_PREFIX = {
    "implementation": "feat",
    "feature": "feat",
    "bug": "fix",
    "refactor": "refactor",
    "docs": "docs",
    "chore": "chore",
    "devops": "devops",
}

# Allowed branch prefixes. Every one of these is now producible by some issue
# type — that is asserted, not assumed (#1948).
ALLOWED_BRANCH_PREFIXES = ("feat", "fix", "refactor", "chore", "docs", "devops")


class UnknownIssueType(KeyError):
    """An issue type carries no branch/commit prefix.

    Raised rather than defaulted. The old ``.get(issue_type, "feat")`` turned a
    vocabulary fork into a silently wrong branch name, which is how four of the
    seven authorable types ended up on ``feat/`` branches and why nobody noticed
    for as long as they did.
    """


class DisallowedBranchPrefix(ValueError):
    """An explicitly supplied branch does not start with an allowed prefix."""


def prefix_for(issue_type: str) -> str:
    """The conventional prefix for ``issue_type``.

    Raises :class:`UnknownIssueType` when the type has no mapping, naming both the
    offending type and the vocabulary it is missing from, because the fix is
    always one of two edits and the caller cannot tell which without being told.
    """
    try:
        return TYPE_TO_PREFIX[issue_type]
    except KeyError:
        raise UnknownIssueType(
            f"issue type {issue_type!r} has no branch/commit prefix. The prefix "
            f"vocabulary is {sorted(TYPE_TO_PREFIX)} and must equal "
            f"issue.schema.json's type enum — either the type is a typo, or the "
            f"schema and this map have drifted apart again (#1948)."
        ) from None


def assert_branch_prefix_allowed(branch: str) -> None:
    """Refuse a branch whose prefix is not in :data:`ALLOWED_BRANCH_PREFIXES`.

    The derived path already checked this; the EXPLICIT ``--branch`` path did not,
    which is how ``TBD/`` reached a live issue. Overriding the derived prefix stays
    legal — the corpus shows deliberate, sensible overrides — but only within the
    declared vocabulary.
    """
    prefix = branch.split("/", 1)[0]
    if prefix not in ALLOWED_BRANCH_PREFIXES:
        raise DisallowedBranchPrefix(
            f"branch {branch!r} carries prefix {prefix!r}, which is not allowed. "
            f"Allowed: {', '.join(ALLOWED_BRANCH_PREFIXES)}."
        )
