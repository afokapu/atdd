# URN: test:author-atdd-substrate:author-issue-body:C014-UNIT-002-undeclared-changed-file-is-a-violation
# Acceptance: acc:author-atdd-substrate:C014-UNIT-002-undeclared-changed-file-is-a-violation
# WMBT: wmbt:author-atdd-substrate:C014
# Phase: RED
# Layer: application
"""C014-UNIT-002 — a file the work changed but never declared is a violation.

The check has always run in ONE direction: declared -> exists. It can confirm
that every claimed path is real, and can never notice a real change that was
never claimed, so an accurate-but-partial declaration is indistinguishable from
a complete one. Measured across this program's own four PRs, #1632 declared 2
of the 16 files it changed and would have passed COMPLETE while omitting
``.github/workflows/atdd-validate.yml`` and ``src/atdd/cli.py``.

That asymmetry is the sharpest form of the defect: declaring less protects you
and declaring accurately exposes you. This fails until the shared checker also
runs changed -> declared (GREEN).
"""
from __future__ import annotations


def _always_resolves(kind: str, path: str) -> bool:
    """A git probe that confirms every claim, so only the reverse pass is under test."""
    return True


def test_c014_unit_002_undeclared_changed_file_is_a_violation():
    from atdd.coach.utils.artifact_claims import (
        RULE_MUST_BE_DECLARED,
        check_artifact_claims,
    )

    report = check_artifact_claims(
        {"created": [], "modified": ["src/atdd/coach/commands/issue.py"], "deleted": []},
        resolves=_always_resolves,
        changed_files=[
            "src/atdd/coach/commands/issue.py",
            ".github/workflows/atdd-validate.yml",
            "src/atdd/cli.py",
        ],
        issue_number=1632,
    )

    undeclared = [v for v in report.violations if v.rule_id == RULE_MUST_BE_DECLARED]
    assert len(undeclared) == 2, (
        "each changed file absent from the claim must be its own violation; "
        f"got {[v.detail for v in report.violations]}"
    )
    reported = " ".join(v.detail for v in undeclared)
    assert ".github/workflows/atdd-validate.yml" in reported
    assert "src/atdd/cli.py" in reported


def test_c014_unit_002_a_complete_declaration_yields_no_violation():
    """Declaring every changed file is the way out — and it must actually work."""
    from atdd.coach.utils.artifact_claims import check_artifact_claims

    report = check_artifact_claims(
        {
            "created": ["src/atdd/coach/utils/artifact_claims.py"],
            "modified": ["src/atdd/coach/commands/issue.py"],
            "deleted": ["src/atdd/legacy.py"],
        },
        resolves=_always_resolves,
        changed_files=[
            "src/atdd/coach/utils/artifact_claims.py",
            "src/atdd/coach/commands/issue.py",
            "src/atdd/legacy.py",
        ],
        issue_number=1726,
    )

    assert report.violations == (), (
        f"a complete, resolving declaration must pass clean; got "
        f"{[str(v) for v in report.violations]}"
    )


def test_c014_unit_002_an_unknown_changed_set_does_not_invent_violations():
    """Where git cannot name the changed set, the reverse pass reports nothing.

    ``changed_files=None`` means "not asked", not "empty". Post-merge with no
    landed commit resolvable, ``main...HEAD`` is empty by construction (#1611)
    and must not be read as "this PR changed nothing".
    """
    from atdd.coach.utils.artifact_claims import check_artifact_claims

    report = check_artifact_claims(
        {"created": [], "modified": ["src/atdd/coach/commands/issue.py"], "deleted": []},
        resolves=_always_resolves,
        changed_files=None,
        issue_number=1726,
    )

    assert report.violations == ()
