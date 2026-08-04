# URN: test:author-atdd-substrate:author-issue-body:C014-UNIT-005-prose-is-not-a-claim-in-any-subsection
# Acceptance: acc:author-atdd-substrate:C014-UNIT-005-prose-is-not-a-claim-in-any-subsection
# WMBT: wmbt:author-atdd-substrate:C014
# Phase: RED
# Layer: application
"""C014-UNIT-005 — prose is not a claim, in any subsection, before git is asked.

The first cut of the checker classified a bullet as prose only AFTER the git
probe had already refused it. That works for ``created`` and ``modified``, where
a nonexistent path fails. It does not work for ``deleted``, where absence is
exactly what the claim expects: ``- None.`` is in no tree, so git reports
CONFIRMED GONE and the bullet passes.

Observed live on #1720 and #1711 — ``Deleted: None. — CONFIRMED GONE`` — which is
this issue's own defect in its fourth form: content that earns a green because
the check it faces cannot fail on it. The order matters, so the order is the
thing under test.
"""
from __future__ import annotations

import pytest

PROSE = ["None.", "No files are deleted by this issue.", "NONE", "none so far"]
KINDS = ("created", "modified", "deleted")


def _claim(kind: str, bullet: str) -> dict:
    artifacts = {k: [] for k in KINDS}
    artifacts[kind] = [bullet]
    return artifacts


def _git_says_deleted_is_gone(kind: str, path: str) -> bool:
    """The real probe's verdict for a path in no tree: deletions are satisfied."""
    return kind == "deleted"


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("bullet", PROSE)
def test_c014_unit_005_prose_is_a_violation_in_every_subsection(kind: str, bullet: str):
    from atdd.coach.utils.artifact_claims import (
        RULE_CLAIMS_RESOLVE,
        check_artifact_claims,
    )

    report = check_artifact_claims(
        _claim(kind, bullet), resolves=_git_says_deleted_is_gone, issue_number=1720,
    )

    assert [v.rule_id for v in report.violations] == [RULE_CLAIMS_RESOLVE], (
        f"{bullet!r} under {kind} is prose, not a path — it must be a violation "
        f"whatever git says; got {[str(v) for v in report.violations]}"
    )
    assert not report.satisfied


def test_c014_unit_005_deleted_prose_is_not_reported_as_confirmed_gone():
    """The exact live symptom: absence must stop reading as satisfaction."""
    from atdd.coach.utils.artifact_claims import check_artifact_claims

    report = check_artifact_claims(
        _claim("deleted", "None."), resolves=_git_says_deleted_is_gone, issue_number=1720,
    )

    rendered = "\n".join(report.messages)
    assert "CONFIRMED GONE" not in rendered, (
        f"prose still earns a deletion's green: {rendered!r}"
    )
    assert "NOT A PATH" in rendered, rendered


def test_c014_unit_005_the_verdict_does_not_depend_on_the_git_probe():
    """Refused before git is asked — the probe is never consulted for prose."""
    from atdd.coach.utils.artifact_claims import check_artifact_claims

    asked = []

    def _probe(kind, path):
        asked.append((kind, path))
        return True

    report = check_artifact_claims(
        _claim("deleted", "None."), resolves=_probe, issue_number=1720,
    )

    assert asked == [], f"git was consulted about prose: {asked}"
    assert report.violations


def test_c014_unit_005_force_does_not_waive_it():
    """``--force`` waives verification against git; this judgement needs none."""
    from atdd.coach.utils.artifact_claims import check_artifact_claims

    report = check_artifact_claims(
        _claim("deleted", "None."),
        resolves=lambda k, p: True,
        force=True,
        issue_number=1720,
    )

    assert report.violations, "--force must not turn prose into a claim"


@pytest.mark.parametrize(
    "kind, path",
    [("created", "src/atdd/cli.py"), ("modified", "CLAUDE.md"), ("deleted", "docs/old.md")],
)
def test_c014_unit_005_real_paths_are_untouched(kind: str, path: str):
    """The guard must not start refusing the claims it exists to verify."""
    from atdd.coach.utils.artifact_claims import check_artifact_claims

    report = check_artifact_claims(
        _claim(kind, path), resolves=lambda k, p: True, issue_number=1726,
    )

    assert report.violations == (), [str(v) for v in report.violations]


def test_c014_unit_005_path_shaped_filler_is_a_known_limitation():
    """What a SHAPE check cannot do, stated rather than implied.

    ``n/a`` has a separator, no whitespace and no trailing period, so it is
    indistinguishable from a real three-character path by shape alone — and a
    deletion claim only asks "is it absent now?", which filler satisfies. So
    ``- n/a`` under ``### Deleted`` still passes.

    Closing that needs a different question, not a stricter pattern: a deletion
    claim should have to EXIST in the parent revision and be gone in the landed
    one. Today the probe asks only the second half. That is a change to the
    revision arithmetic in ``IssueManager`` (#1611 territory), so it is recorded
    here as a bounded gap rather than smuggled in — this test pins the current
    behaviour so the day someone fixes it, this is the test that tells them.
    """
    from atdd.coach.utils.artifact_claims import check_artifact_claims

    report = check_artifact_claims(
        _claim("deleted", "n/a"), resolves=_git_says_deleted_is_gone, issue_number=1720,
    )

    assert report.violations == (), (
        "behaviour changed — if a deletion claim now has to have existed first, "
        "delete this test and fold `n/a` back into the PROSE fixture above"
    )
