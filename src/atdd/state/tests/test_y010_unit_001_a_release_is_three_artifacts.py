# URN: test:govern-lifecycle:release-state-is-observed-not-inferred:Y010-UNIT-001-a-release-is-three-artifacts
# Acceptance: acc:govern-lifecycle:Y010-UNIT-001-a-release-is-three-artifacts
# WMBT: wmbt:govern-lifecycle:Y010
# Phase: GREEN
# Layer: backend.unit
"""Y010-UNIT-001 — a release is three artifacts that fail independently (#1924).

`publish.yml` decided "already released" from `git describe --exact-match` alone.
A release is a git tag, a PyPI wheel and a GitHub Release object, published in
that order by separate calls that fail separately. The tag is created FIRST, so
it is the artifact most likely to exist when a later step fails — which makes the
tag the worst possible proxy for the whole.

Measured: `v4.73.0` and `v4.73.1` both carry a tag and a wheel and neither has a
release object. `v4.72.0`, the last complete one, has all three.

The second assertion here is the one that is easy to miss. Reporting PARTIAL is
not enough on its own: if a PARTIAL run then follows the ordinary reconcile+bump
path it publishes the NEXT version and abandons the half-published one forever.
So PARTIAL must name the version to COMPLETE, not a version to mint.
"""
from __future__ import annotations

import itertools

import pytest

from atdd.state.version import (
    ABSENT,
    COMPLETE,
    PARTIAL,
    ReleaseArtifacts,
    plan_release_action,
    release_state,
)


def test_all_three_present_is_complete() -> None:
    assert release_state(ReleaseArtifacts(True, True, True)) == COMPLETE


def test_none_present_is_absent() -> None:
    assert release_state(ReleaseArtifacts(False, False, False)) == ABSENT


@pytest.mark.parametrize("tag,pypi,release", [
    combo for combo in itertools.product([True, False], repeat=3)
    if any(combo) and not all(combo)
])
def test_any_mixture_is_partial(tag: bool, pypi: bool, release: bool) -> None:
    """Six of the eight states are partial. The old gate called three of them
    'released' because it only ever looked at the first field."""
    assert release_state(ReleaseArtifacts(tag, pypi, release)) == PARTIAL


def test_the_state_that_actually_happened_is_not_released() -> None:
    """v4.73.0 and v4.73.1: tag and wheel published, release object never created."""
    art = ReleaseArtifacts(tag=True, pypi=True, github_release=False)
    assert release_state(art) == PARTIAL
    assert art.missing() == ["github-release"]


def test_partial_completes_the_existing_version_and_never_bumps() -> None:
    """THE TRAP. Flipping the gate to 'not released' without this sends the run
    down reconcile+bump, publishing 4.73.2 and abandoning 4.73.1 permanently."""
    plan = plan_release_action(
        head_version="4.73.1",
        artifacts=ReleaseArtifacts(True, True, False),
        next_version="4.73.2",
    )
    assert plan.action == "complete"
    assert plan.version == "4.73.1", "a partial release must never be bumped past"
    assert plan.missing == ["github-release"]


def test_complete_skips_so_a_rerun_is_idempotent() -> None:
    """No duplicate tag, no duplicate upload."""
    plan = plan_release_action("4.73.1", ReleaseArtifacts(True, True, True), "4.73.2")
    assert plan.action == "skip"
    assert plan.missing == []


def test_absent_publishes_the_next_version_as_before() -> None:
    """The ordinary path is unchanged — this must not stop normal releases."""
    plan = plan_release_action("4.73.1", ReleaseArtifacts(False, False, False), "4.73.2")
    assert plan.action == "publish-new"
    assert plan.version == "4.73.2"


def test_without_a_tag_there_is_no_version_to_complete() -> None:
    """The tag is the IDENTITY, not merely one artifact of three.

    `head_version` is derived from the tag on HEAD, so with no tag there is
    nothing to name — artifacts elsewhere are orphans this commit cannot claim.
    That is the boundary #1326's max(PyPI, git tag) base already covers: it stops
    the next version colliding, it does not heal the orphan.
    """
    plan = plan_release_action(
        head_version=None,
        artifacts=ReleaseArtifacts(tag=False, pypi=True, github_release=True),
        next_version="4.73.2",
    )
    assert plan.action == "publish-new"
    assert plan.version == "4.73.2"
    assert plan.orphaned, (
        "artifacts exist for a version this commit cannot name; the run must say so "
        "rather than publish over it in silence"
    )
