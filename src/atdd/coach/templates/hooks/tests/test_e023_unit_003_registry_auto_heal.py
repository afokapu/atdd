# URN: test:govern-lifecycle:close-substrate-friction-regressions:E023-UNIT-003-registry-check-auto-heals-in-non-ci
# Acceptance: acc:govern-lifecycle:E023-UNIT-003-registry-check-auto-heals-in-non-ci
# WMBT: wmbt:govern-lifecycle:E023
# Phase: GREEN
# Layer: backend.unit
"""AC-UNIT-003: the registry check heals drift automatically instead of blocking
the operator — and it heals from the hook stage where that is possible.

E023 chose self-heal over a manual remediation loop, and that intent stands. What
it got wrong was the location: the heal was placed in pre-push, where git has
already resolved the refs it will send (they arrive on the hook's stdin), so a
staged file can never reach the push. The hook printed "resynced and re-staged"
and pushed the drifted mirror anyway, leaving the fix uncommitted (#1888).

The heal now runs from pre-commit, where a staged file still joins the commit
being created. These assertions are therefore directional: the heal must be in
pre-commit, and pre-push must NOT stage the mirrors.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOKS_DIR = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks"
PRE_COMMIT = HOOKS_DIR / "pre-commit"
PRE_PUSH = HOOKS_DIR / "pre-push"

_MIRROR_STAGE = "git add plan/_wagons.yaml plan/_trains.yaml contracts/_artifacts.yaml"


def _executable_lines(hook: Path) -> list[str]:
    """Lines the shell would actually run: no comments, no heredoc bodies.

    The drift message quotes the remedy — `git add plan/_wagons.yaml ...` — as
    text for the operator to copy. That is instruction, not execution, and a
    guard that cannot tell the two apart would either fire on the help text or
    have to stop looking for the thing it exists to catch.
    """
    out: list[str] = []
    terminator: str | None = None
    for raw in hook.read_text(encoding="utf-8").splitlines():
        if terminator is not None:
            if raw.strip() == terminator:
                terminator = None
            continue
        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        if "<<" in raw:
            tag = raw.split("<<", 1)[1].strip().lstrip("-").strip()
            if tag:
                terminator = tag.strip("'\"")
                continue
        out.append(raw)
    return out


def test_pre_commit_hook_has_the_registry_auto_heal() -> None:
    """The heal runs where staging still reaches the commit."""
    text = PRE_COMMIT.read_text(encoding="utf-8")
    assert "atdd registry update --yes" in text, (
        f"{PRE_COMMIT} does not run the resync.\n"
        "E023's self-heal intent requires the operator not be sent round a manual\n"
        "remediation loop; pre-commit is the only hook where the resync can join\n"
        "the commit the operator is already making."
    )
    assert _MIRROR_STAGE in text, (
        "The resync must be staged in pre-commit, or it will not be part of the commit."
    )


def test_auto_heal_notice_names_the_command_it_ran() -> None:
    text = PRE_COMMIT.read_text(encoding="utf-8")
    assert "registry update --yes" in text and "resynced" in text, (
        "The notice must name the command that ran, so the operator can see what\n"
        "was done to their commit without reading the hook."
    )


def test_pre_push_does_not_stage_the_mirrors() -> None:
    """THE REGRESSION GUARD (#1888).

    Staging in pre-push is not merely useless — it reports success and ships the
    drift. Any reintroduction of a mirror `git add` there must fail this test.
    """
    staging_lines = [
        ln for ln in _executable_lines(PRE_PUSH)
        if "git add" in ln and "_wagons.yaml" in ln
    ]
    assert not staging_lines, (
        "pre-push stages the registry mirrors again:\n  "
        + "\n  ".join(staging_lines)
        + "\n\ngit resolves the refs it will push BEFORE running this hook, so nothing\n"
        "staged here reaches the remote. The heal belongs in pre-commit."
    )


def test_pre_push_does_not_claim_a_heal_it_cannot_perform() -> None:
    """The shipped defect was a success notice, not a missing fix."""
    for claim in ("auto-resynced", "re-staged; continuing push"):
        offenders = [
            ln for ln in _executable_lines(PRE_PUSH)
            if claim in ln and "echo" in ln
        ]
        assert not offenders, (
            f"pre-push prints a claim it cannot honour ({claim!r}):\n  "
            + "\n  ".join(offenders)
        )
