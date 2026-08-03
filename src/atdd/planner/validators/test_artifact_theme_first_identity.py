# URN: component:atdd-plan-core:naming:ArtifactThemeFirstIdentity:backend:tests
# Acceptance: acc:define-plans:C005-SMOKE-001-theme-first-blocks-at-confirm
# Acceptance: acc:define-plans:C005-SMOKE-002-cli-exit-nonzero-on-artifact-naming-refusal
# Acceptance: acc:define-plans:E003-SMOKE-001-artifact-naming-rules-bound-and-run
# WMBT: wmbt:define-plans:C005
# Phase: SMOKE
# Runtime: python
# Purpose: Foundational artifact identity (theme-first) is validator-backed and blocks at Confirm (#1329).
"""Validators for ``planner.artifact-naming.theme-first-identity`` (#1329).

Artifact/contract naming was prose-only guidance in
``artifact-naming.convention.yaml``; #1329 promotes the theme-first identity to a
bound, confirm-blocking rule — the artifact analogue of the #1276 verb-object
treatment. These tests pin:

* the rule is registered (``bind_rule`` resolves it),
* the pure mechanic — theme-first grammar, kebab-case tokens, and
  ``theme ∈ get_theme_map`` — accepts good identities and rejects the real-world
  bad one from the issue (``round:result``, where ``round`` is not a theme), and
* ``PlanSession.confirm`` refuses to lock a kept wagon whose produced artifact is
  not theme-first, while a theme-first identity locks normally (the missing teeth).
"""
from __future__ import annotations

import json

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.artifact_naming import is_valid_artifact_identity
from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit, Verdict,
)

# Good theme-first identities — the convention's own canonical examples. Themes
# resolve from the built-in default map (no .atdd/config.yaml in the tmp repos).
GOOD = [
    "commons:identifiers.uuid",
    "commons:ux:foundations:color",
    "commons:ux:foundations:color.primary",
    "sensory:gesture.raw",
    "match:config",
    "scenario:fragments",
]

# Real / structural failures: a non-taxonomy theme (the issue's motivation),
# non-kebab tokens, a themeless name, and an over-specified variant.
BAD = ["round:result", "Bad:Theme", "gesture", "commons:", "commons:id.a.b"]


def test_rule_is_bound() -> None:
    rule = bind_rule("planner.artifact-naming.theme-first-identity")
    assert rule.rule_id == "planner.artifact-naming.theme-first-identity"


@pytest.mark.parametrize("name", GOOD)
def test_good_identities_pass(name: str) -> None:
    ok, reason = is_valid_artifact_identity(name)
    assert ok, f"{name!r} should be theme-first but failed: {reason}"


@pytest.mark.parametrize("name", BAD)
def test_bad_identities_fail(name: str) -> None:
    ok, reason = is_valid_artifact_identity(name)
    assert not ok, f"{name!r} should violate theme-first identity but passed"
    assert reason, "a violation must carry a human-readable reason"


def _confirm_session_producing(name: str) -> PlanSession:
    """A confirm-step session with one kept, verb-object wagon that produces the
    artifact ``name`` — verb-object slug so the earlier verb-object gate passes
    and the artifact-naming gate is the one under test."""
    s = PlanSession(session_id="a1")
    s.step = Step.RATIFY.value
    s.issue_ref = "demo-slug"
    s.add_unit(Unit(kind="wagon", ref="wagon:manage-users", verdict=Verdict.KEEP.value,
                    spec={"wagon": "manage-users",
                          "produce": [{"name": name, "contract": None}]}))
    return s


def test_confirm_blocks_non_theme_first_artifact(tmp_path) -> None:
    s = _confirm_session_producing("round:result")
    with pytest.raises(SessionGateError):
        s.confirm(root=tmp_path)
    assert s.locked is False


def test_confirm_locks_theme_first_artifact(tmp_path) -> None:
    s = _confirm_session_producing("commons:identifiers.uuid")
    s.confirm(root=tmp_path)
    assert s.locked is True


def _drive_cli_to_confirm(tmp_path, produced_name: str) -> int:
    """Drive the real ``atdd plan`` CLI dispatch from start through confirm with
    one kept wagon that produces ``produced_name``; return confirm's exit code."""
    from atdd.planner.commands.plan_session_cli import run

    root = str(tmp_path)
    spec = json.dumps({"wagon": "manage-users",
                       "produce": [{"name": produced_name, "contract": None}]})
    assert run(["--root", root, "start", "--id", "c1",
                "--main-job", "mj", "--issue", "demo-slug"]) == 0
    assert run(["--root", root, "source", "--id", "c1", "req"]) == 0
    assert run(["--root", root, "advance", "--id", "c1", "--step", "attach"]) == 0
    assert run(["--root", root, "advance", "--id", "c1", "--step", "compose"]) == 0
    assert run(["--root", root, "unit", "--id", "c1", "--kind", "wagon",
                "--ref", "wagon:manage-users", "--spec", spec]) == 0
    assert run(["--root", root, "decide", "--id", "c1",
                "--ref", "wagon:manage-users", "--verdict", "keep"]) == 0
    assert run(["--root", root, "advance", "--id", "c1", "--step", "ratify"]) == 0
    return run(["--root", root, "confirm", "--id", "c1"])


def test_confirm_cli_exits_nonzero_on_artifact_naming_refusal(tmp_path) -> None:
    """`atdd plan confirm` must exit non-zero when the theme-first gate refuses a
    produced artifact, and 0 when the identity is theme-first (#1329)."""
    assert _drive_cli_to_confirm(tmp_path / "bad", "round:result") != 0
    assert _drive_cli_to_confirm(tmp_path / "good", "commons:identifiers.uuid") == 0
