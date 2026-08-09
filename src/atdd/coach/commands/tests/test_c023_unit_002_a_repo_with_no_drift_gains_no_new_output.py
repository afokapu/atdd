# URN: test:govern-lifecycle:enforcing-artifact-declaration:C023-UNIT-002-a-repo-with-no-drift-gains-no-new-output
# Acceptance: acc:govern-lifecycle:C023-UNIT-002-a-repo-with-no-drift-gains-no-new-output
# WMBT: wmbt:govern-lifecycle:C023
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""
AC-UNIT-002: the clean path is untouched.

The cheap way to satisfy AC-UNIT-001 is to print the declaration warning
unconditionally. That would put an Artifacts lecture in front of every operator
on every clean check, and the warning would stop meaning anything on the one run
where it is true. This pins the in-sync branch byte-for-byte.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.registry import RegistryBuilder


# What check mode printed for an in-sync registry before #1739, verbatim.
CLEAN_OUTPUT = "\n✅ Wagon registry is in sync\n"


@pytest.fixture()
def builder(tmp_path: Path) -> RegistryBuilder:
    return RegistryBuilder(tmp_path)


def _check_in_sync(builder: RegistryBuilder) -> dict:
    """Run check mode over a registry the scan found nothing to change in."""
    return builder._confirm_and_apply(
        "check",
        "wagon",
        builder.plan_dir / "_wagons.yaml",
        {"wagons": []},
        {"new": 0, "changes": []},
    )


def test_the_clean_path_output_is_unchanged(builder, capsys):
    """Byte-identical to the pre-#1739 in-sync output — not merely 'contains'."""
    _check_in_sync(builder)
    captured = capsys.readouterr()
    assert captured.out == CLEAN_OUTPUT, (
        "a repo with no drift must produce no new output on the clean path.\n"
        f"expected: {CLEAN_OUTPUT!r}\nactual:   {captured.out!r}"
    )
    assert captured.err == "", f"the clean path must write nothing to stderr: {captured.err!r}"


@pytest.mark.parametrize(
    "leaked",
    ["## Artifacts", "git diff --name-only", "--amend", "atdd registry update --yes"],
)
def test_no_remediation_text_leaks_into_the_clean_path(builder, capsys, leaked):
    """None of the drift remediation — old or new — reaches an in-sync run."""
    _check_in_sync(builder)
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert leaked not in output, (
        f"{leaked!r} must not appear when the registry is in sync. Got:\n{output}"
    )


def test_drift_is_the_discriminator(builder, capsys):
    """The control: the same call site with a change recorded does warn, so the
    silence above is the absence of drift and not an unreachable branch."""
    builder._confirm_and_apply(
        "check",
        "wagon",
        builder.plan_dir / "_wagons.yaml",
        {"wagons": []},
        {"new": 1, "changes": [{"wagon": "my-wagon", "type": "new", "fields": ["all"]}]},
    )
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "## Artifacts" in output, (
        f"the drifted run must carry the declaration warning. Got:\n{output}"
    )
    assert "git diff --name-only origin/main..HEAD" in output, (
        f"the drifted run must carry the re-derivation command. Got:\n{output}"
    )
