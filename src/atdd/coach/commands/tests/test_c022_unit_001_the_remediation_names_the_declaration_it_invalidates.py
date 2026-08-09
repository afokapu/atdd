# URN: test:govern-lifecycle:enforcing-artifact-declaration:C022-UNIT-001-the-remediation-names-the-declaration-it-invalidates
# Acceptance: acc:govern-lifecycle:C022-UNIT-001-the-remediation-names-the-declaration-it-invalidates
# WMBT: wmbt:govern-lifecycle:C022
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""
AC-UNIT-001: the drift remediation names the ``## Artifacts`` declaration the
amend it prescribes invalidates, and names the re-derivation to run.

``format_fix_hint`` ends with ``git add <mirrors> && git commit --amend
--no-edit``. The issue's ``## Artifacts`` section was authored from
``git diff --name-only origin/main..HEAD`` as that diff stood *before* the
resync, so the amend leaves the declaration stale by exactly the mirrors it
appends — and since #1726 the REFACTOR -> COMPLETE gate refuses undeclared
paths. The hint is the one place that knows, at the moment it prints, which
files are about to be appended.
"""
from __future__ import annotations

from atdd.coach.commands.registry import MIRROR_FILES, format_fix_hint


DRIFTED = ["plan/_wagons.yaml", "contracts/_artifacts.yaml"]


def test_the_working_remediation_survives():
    """The warning is added to the instruction, not traded for it."""
    hint = format_fix_hint({"drifted_files": DRIFTED})
    assert "atdd registry update --yes" in hint, (
        f"the resync command must survive the added warning. Got:\n{hint}"
    )
    assert "git commit --amend --no-edit" in hint, (
        f"the re-stage-and-amend instruction must survive the added warning. Got:\n{hint}"
    )


def test_the_hint_names_the_artifacts_section_and_the_amend_as_its_cause():
    """Telling the operator a declaration exists is not enough — the hint must
    say the amend it just prescribed is what makes that declaration stale."""
    hint = format_fix_hint({"drifted_files": DRIFTED})
    assert "## Artifacts" in hint, (
        f"the hint must name the `## Artifacts` section by its heading. Got:\n{hint}"
    )
    assert "stale" in hint.lower(), (
        f"the hint must say the declaration is left stale, not merely that one exists. "
        f"Got:\n{hint}"
    )
    # The consequence has to follow the instruction that causes it; a warning
    # printed before the amend reads as being about some other commit.
    assert hint.index("git commit --amend --no-edit") < hint.index("## Artifacts"), (
        "the declaration consequence must follow the amend it is the consequence of. "
        f"Got:\n{hint}"
    )


def test_the_hint_names_the_mechanical_re_derivation():
    """A warning that does not name the derivation the gate applies leaves the
    author to guess at it."""
    hint = format_fix_hint({"drifted_files": DRIFTED})
    assert "git diff --name-only origin/main..HEAD" in hint, (
        "the hint must name the mechanical re-derivation for `## Artifacts`. "
        f"Got:\n{hint}"
    )


def test_the_amend_and_the_warning_describe_one_set_of_files():
    """The files the amend re-stages come from the same named set the warning is
    about — not from a second hard-coded list that can drift from the first."""
    hint = format_fix_hint({"drifted_files": DRIFTED})
    for mirror in MIRROR_FILES:
        assert mirror in hint, (
            f"the re-stage instruction must name mirror {mirror!r}. Got:\n{hint}"
        )
    for drifted in DRIFTED:
        assert drifted in hint, (
            f"the hint must name drifted file {drifted!r}. Got:\n{hint}"
        )


def test_an_empty_drift_report_still_carries_the_consequence():
    """A call site that reports no per-file detail must not silently drop the
    warning — it degrades to naming the mirrors generically."""
    hint = format_fix_hint({})
    assert "## Artifacts" in hint, (
        f"the consequence must survive an empty drift report. Got:\n{hint}"
    )
    assert "git diff --name-only origin/main..HEAD" in hint, (
        f"the re-derivation must survive an empty drift report. Got:\n{hint}"
    )
