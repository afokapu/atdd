# URN: component:atdd-plan-core:naming:ArtifactPathMirrorsIdentity:backend:tests
# Acceptance: acc:define-plans:C006-SMOKE-001-path-mirror-blocks-at-confirm
# Acceptance: acc:define-plans:E003-SMOKE-001-artifact-naming-rules-bound-and-run
# WMBT: wmbt:define-plans:C006
# Phase: SMOKE
# Runtime: python
# Purpose: A produced contract path must mirror its artifact identity and blocks at Confirm (#1329).
"""Validators for ``planner.artifact-naming.path-mirrors-identity`` (#1329).

The contract-file-mapping (identity -> ``contracts/…/{aspect}.schema.json``) was
prose in ``artifact-naming.convention.yaml``; #1329 makes a mis-located
``.schema.json`` a confirm-blocking violation. These tests pin:

* the rule is registered (``bind_rule`` resolves it),
* the pure mechanic accepts the convention's own contract paths (including both
  physical forms of the simple ``theme:aspect`` identity) and rejects a schema
  landing under the wrong directory, and
* ``PlanSession.confirm`` refuses to lock a kept wagon whose produced contract
  path does not mirror the identity, while a mirrored path locks normally.
"""
from __future__ import annotations

import json

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner.artifact_naming import path_mirrors_identity
from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit, Verdict,
)

# (identity, contract_path) pairs that mirror correctly — straight from the
# convention's contract_file_mapping / logical_vs_physical examples.
GOOD = [
    ("commons:identifiers.uuid", "contracts/commons/identifiers/uuid.schema.json"),
    ("commons:ux:foundations:color", "contracts/commons/ux/foundations/color.schema.json"),
    ("commons:ux:foundations:color.primary", "contracts/commons/ux/foundations/color/primary.schema.json"),
    ("sensory:gesture.raw", "contracts/sensory/gesture/raw.schema.json"),
    ("match:config", "contracts/match/config/config.schema.json"),
    ("scenario:fragment", "contracts/scenario/fragment/fragment.schema.json"),
]

# A schema file that does not mirror its identity (wrong middle directory).
BAD = [
    ("commons:identifiers.uuid", "contracts/commons/WRONG/uuid.schema.json"),
    ("sensory:gesture.raw", "contracts/sensory/gesture.schema.json"),
]


def test_rule_is_bound() -> None:
    rule = bind_rule("planner.artifact-naming.path-mirrors-identity")
    assert rule.rule_id == "planner.artifact-naming.path-mirrors-identity"


@pytest.mark.parametrize("name,path", GOOD)
def test_mirrored_paths_pass(name: str, path: str) -> None:
    ok, reason = path_mirrors_identity(name, path)
    assert ok, f"{path!r} should mirror {name!r} but failed: {reason}"


@pytest.mark.parametrize("name,path", BAD)
def test_mispathed_contracts_fail(name: str, path: str) -> None:
    ok, reason = path_mirrors_identity(name, path)
    assert not ok, f"{path!r} should not mirror {name!r} but passed"
    assert reason, "a violation must carry a human-readable reason"


def _confirm_session_producing(name: str, contract: str) -> PlanSession:
    s = PlanSession(session_id="p1")
    s.step = Step.CONFIRM.value
    s.issue_ref = "demo-slug"
    s.add_unit(Unit(kind="wagon", ref="wagon:manage-users", verdict=Verdict.KEEP.value,
                    spec={"wagon": "manage-users",
                          "produce": [{"name": name, "contract": contract}]}))
    return s


def test_confirm_blocks_mispathed_contract(tmp_path) -> None:
    s = _confirm_session_producing(
        "commons:identifiers.uuid", "contracts/commons/WRONG/uuid.schema.json")
    with pytest.raises(SessionGateError):
        s.confirm(root=tmp_path)
    assert s.locked is False


def test_confirm_locks_mirrored_contract(tmp_path) -> None:
    s = _confirm_session_producing(
        "commons:identifiers.uuid", "contracts/commons/identifiers/uuid.schema.json")
    s.confirm(root=tmp_path)
    assert s.locked is True


def _drive_cli_to_confirm(tmp_path, name: str, contract: str) -> int:
    from atdd.planner.commands.plan_session_cli import run

    root = str(tmp_path)
    spec = json.dumps({"wagon": "manage-users",
                       "produce": [{"name": name, "contract": contract}]})
    assert run(["--root", root, "start", "--id", "c1",
                "--main-job", "mj", "--issue", "demo-slug"]) == 0
    assert run(["--root", root, "source", "--id", "c1", "req"]) == 0
    assert run(["--root", root, "advance", "--id", "c1", "--step", "locate"]) == 0
    assert run(["--root", root, "advance", "--id", "c1", "--step", "prepare"]) == 0
    assert run(["--root", root, "unit", "--id", "c1", "--kind", "wagon",
                "--ref", "wagon:manage-users", "--spec", spec]) == 0
    assert run(["--root", root, "decide", "--id", "c1",
                "--ref", "wagon:manage-users", "--verdict", "keep"]) == 0
    assert run(["--root", root, "advance", "--id", "c1", "--step", "confirm"]) == 0
    return run(["--root", root, "confirm", "--id", "c1"])


def test_confirm_cli_exits_nonzero_on_mispathed_contract(tmp_path) -> None:
    assert _drive_cli_to_confirm(
        tmp_path / "bad", "commons:identifiers.uuid",
        "contracts/commons/WRONG/uuid.schema.json") != 0
    assert _drive_cli_to_confirm(
        tmp_path / "good", "commons:identifiers.uuid",
        "contracts/commons/identifiers/uuid.schema.json") == 0
