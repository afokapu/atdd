# URN: component:govern-lifecycle:enforcement-substrate:test_session_naming:backend:domain
# Runtime: python
# Purpose: Helper unit tests for canonical session-name + layout helpers (issue #470).

"""Unit tests for ``atdd.coach.utils.session_naming``."""

from __future__ import annotations

import pytest

from atdd.coach.utils.session_naming import (
    CANONICAL_NAME_REGEX,
    branch_to_slug,
    compute_canonical_name,
    compute_repo_short_name,
    is_canonical_name,
    parse_canonical_name,
    target_grid_label,
    truncate_slug,
)


pytestmark = [pytest.mark.coach]


# ---------------------------------------------------------------------------
# compute_canonical_name + parse_canonical_name round-trips
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "repo, issue, slug, phase, expected",
    [
        ("ATDD", 470, "canonical-session-naming", None, "ATDD470-canonical-session-naming"),
        ("ATDD", 462, "bump-on-merge", 2, "ATDD462-phase2-bump-on-merge"),
        ("JEL", 1, "x", None, "JEL1-x"),
        ("ATDD", 467, "hint-completeness", None, "ATDD467-hint-completeness"),
    ],
)
def test_compute_canonical_name(repo, issue, slug, phase, expected):
    assert compute_canonical_name(repo, issue, slug, phase=phase) == expected


@pytest.mark.parametrize(
    "name, parts",
    [
        ("ATDD470-foo", ("ATDD", 470, None, "foo")),
        ("ATDD462-phase2-bump-on-merge", ("ATDD", 462, 2, "bump-on-merge")),
        ("JEL12-a-b-c", ("JEL", 12, None, "a-b-c")),
    ],
)
def test_parse_canonical_name(name, parts):
    parsed = parse_canonical_name(name)
    assert parsed is not None
    assert (parsed.repo, parsed.issue, parsed.phase, parsed.slug) == parts


@pytest.mark.parametrize(
    "name",
    [
        "",
        "atdd470-foo",      # lowercase repo
        "A470-foo",          # repo too short
        "TOOLONGREPO470-foo",
        "ATDD-foo",          # missing number
        "ATDD470-Foo",       # uppercase in slug
        "ATDD470-",          # empty slug
    ],
)
def test_parse_rejects_non_canonical(name):
    assert parse_canonical_name(name) is None
    assert is_canonical_name(name) is False


# ---------------------------------------------------------------------------
# Regex coverage — the helper regex agrees with the convention's intent
# ---------------------------------------------------------------------------
def test_canonical_regex_anchored():
    # Anchored at both ends — substring drift is rejected.
    assert CANONICAL_NAME_REGEX.match("xATDD470-foo") is None
    # Whitespace inside the slug is rejected (trailing space, internal space).
    assert CANONICAL_NAME_REGEX.match("ATDD470-foo bar") is None
    assert CANONICAL_NAME_REGEX.match("ATDD470-foo!") is None


# ---------------------------------------------------------------------------
# branch_to_slug
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "branch, expected",
    [
        ("feat/470-canonical-session-naming", "470-canonical-session-naming"),
        ("fix/typo", "typo"),
        ("refactor/four-layer", "four-layer"),
        ("chore/cleanup", "cleanup"),
        ("docs/readme", "readme"),
        ("devops/release", "release"),
        ("nameonly", "nameonly"),
        ("", ""),
    ],
)
def test_branch_to_slug(branch, expected):
    assert branch_to_slug(branch) == expected


# ---------------------------------------------------------------------------
# compute_repo_short_name
# ---------------------------------------------------------------------------
def test_compute_repo_short_name_explicit_field():
    config = {"repo": {"short_name": "atdd"}}
    assert compute_repo_short_name(config) == "ATDD"


def test_compute_repo_short_name_from_github_repo():
    config = {"github": {"repo": "afokapu/atdd"}}
    assert compute_repo_short_name(config) == "ATDD"


def test_compute_repo_short_name_from_hyphenated_repo():
    config = {"github": {"repo": "afokapu/jel-app"}}
    assert compute_repo_short_name(config) == "APP"


def test_compute_repo_short_name_fallback():
    assert compute_repo_short_name({}) == "REPO"
    assert compute_repo_short_name(None) == "REPO"


# ---------------------------------------------------------------------------
# truncate_slug
# ---------------------------------------------------------------------------
def test_truncate_slug_short():
    assert truncate_slug("short-slug") == "short-slug"


def test_truncate_slug_word_boundary():
    long_slug = "a-very-long-slug-that-exceeds-the-forty-char-limit"
    truncated = truncate_slug(long_slug)
    assert len(truncated) <= 40
    # Word-boundary truncation: result ends at a hyphen-bounded token
    assert "-" in truncated
    assert not truncated.endswith("-")


def test_truncate_slug_no_hyphen():
    # No hyphens → falls back to a hard cut.
    assert truncate_slug("a" * 60) == "a" * 40


# ---------------------------------------------------------------------------
# target_grid_label
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "n, contains",
    [
        (0, "shell-only"),
        (1, "1 surface"),
        (2, "stacked vertically"),
        (3, "2x2"),
        (4, "2x2"),
        (5, "2x3"),
        (6, "2x3"),
        (7, "dense column grid"),
        (12, "dense column grid"),
    ],
)
def test_target_grid_label(n, contains):
    assert contains in target_grid_label(n)


def test_target_grid_label_negative_clamps_to_zero():
    assert "shell-only" in target_grid_label(-3)
