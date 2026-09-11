# URN: test:govern-lifecycle:worktree-name-is-a-valid-refname:Y009-UNIT-001-a-store-slug-becomes-a-valid-refname
# Acceptance: acc:govern-lifecycle:Y009-UNIT-001-a-store-slug-becomes-a-valid-refname
# WMBT: wmbt:govern-lifecycle:Y009
# Phase: GREEN
# Layer: backend.unit
"""Y009-UNIT-001 — a store slug is reduced to something git accepts (#1913).

`WorkItemReader.session_entry` returns ``{"slug": obj.uid, ...}`` — the slug IS
the uid — and for records predating the authoring path the uid is
``unverified:<slug>``. `atdd worktree create` built ``feat/<slug>`` from it and
git refused every one: a colon is illegal in a refname.

Correctness here is decided by **git**, not by my reading of the rules, so every
case is checked with `git check-ref-format --branch` rather than against a
transcribed regex. The rules are fiddly (``..``, ``@{``, a trailing ``.lock``,
leading/trailing dots) and a hand-copied list is exactly the kind of second
implementation this repository keeps finding.

The load-bearing property is the identity one: a slug git already accepts must
come back unchanged. Existing branch↔issue bindings are derived from these
strings, so a sanitizer that "improves" a valid slug would silently move them.
"""
from __future__ import annotations

import subprocess

import pytest

from atdd.coach.commands.worktree_placement import (
    resolve_worktree_dir_name,
    sanitize_branch_slug,
)


def _git_accepts(branch: str) -> bool:
    return subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        capture_output=True,
    ).returncode == 0


ALREADY_VALID = [
    "repair-interlocking-coverage-validators",
    "issue-1223-review",
    "wi_01JQ8ZK3ABCD",
    "stale-version-cache-advertises-phantom-upgrade",
]

REFUSED_BY_GIT = [
    "unverified:issue-814",
    "unverified:some-real-slug",
    "has space",
    "tilde~thing",
    "caret^thing",
    "question?mark",
    "star*",
    "brack[et",
    "back\\slash",
    "dot..dot",
    "at@{brace",
    ".leading-dot",
    "trailing-dot.",
    "ends.lock",
]


@pytest.mark.parametrize("slug", ALREADY_VALID)
def test_a_valid_slug_is_returned_unchanged(slug: str) -> None:
    """THE LOAD-BEARING PROPERTY: bindings are derived from these strings."""
    assert _git_accepts(f"feat/{slug}"), "fixture is wrong: git already refuses this"
    assert sanitize_branch_slug(slug) == slug


@pytest.mark.parametrize("slug", REFUSED_BY_GIT)
def test_a_slug_git_refuses_becomes_one_it_accepts(slug: str) -> None:
    """THE DEFECT for the `unverified:` cases; the rest guard the same edge."""
    assert not _git_accepts(f"feat/{slug}"), "fixture is wrong: git accepts this already"
    safe = sanitize_branch_slug(slug)
    assert safe, f"nothing survived sanitizing {slug!r}"
    assert _git_accepts(f"feat/{safe}"), (
        f"{slug!r} sanitized to {safe!r}, which git still refuses"
    )


def test_the_provenance_qualifier_is_stripped_not_mangled() -> None:
    """`unverified:` describes provenance, not identity — the slug under it is
    the real name and must survive intact."""
    assert sanitize_branch_slug("unverified:stale-version-cache") == "stale-version-cache"


def test_a_slug_that_sanitizes_to_nothing_is_refused_not_guessed() -> None:
    """A degenerate uid must not yield `feat-`. The caller substitutes
    `issue-<N>`; emitting a half-formed name would be worse than saying nothing."""
    assert sanitize_branch_slug("unverified:") == ""
    with pytest.raises(ValueError, match="no valid worktree name"):
        resolve_worktree_dir_name("feat", "unverified:")


def test_the_directory_name_is_sanitized_at_the_seam() -> None:
    """Sanitizing lives in the placement seam so the five derivation sites cannot
    disagree — the reason `resolve_worktree_path` exists at all."""
    assert resolve_worktree_dir_name("feat", "unverified:issue-814") == "feat-issue-814"
    assert resolve_worktree_dir_name("fix", "already-fine") == "fix-already-fine"
