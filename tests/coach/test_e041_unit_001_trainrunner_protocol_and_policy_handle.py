# URN: test:govern-lifecycle:extract-workflow-issue-runner-and-workflow-runner-protocol:E041-UNIT-001-trainrunner-protocol-and-policy-handle
# Acceptance: acc:govern-lifecycle:E041-UNIT-001-trainrunner-protocol-and-policy-handle
"""Unit test for E041-UNIT-001 (docs/coach-decomposition.md §4.7, §3.3).

``atdd.train.runner_iface`` defines the §4.7 ``TrainRunner`` Protocol
(start_issue / resume / run_wave / handle_event / status / cancel) and the frozen
``PolicyHandle`` bundle (coach_module + conventions) the CLI constructs.
"""
from __future__ import annotations

import ast
import dataclasses
import typing
from pathlib import Path

import pytest

import atdd
from atdd.coach import core as coach_core
from atdd.coach.core.types import Conventions
from atdd.train.persistence import load_conventions
from atdd.train.runner_iface import PolicyHandle, TrainRunner

from tests.coach._e040_helpers import build_temp_repo


def test_trainrunner_is_a_protocol_with_the_section_4_7_surface():
    assert issubclass(type(TrainRunner), type(typing.Protocol))  # it is a Protocol class
    for method in ("start_issue", "resume", "run_wave", "handle_event", "status", "cancel"):
        assert hasattr(TrainRunner, method), f"TrainRunner missing {method!r}"


def test_policy_handle_is_a_frozen_bundle_of_module_and_conventions(tmp_path):
    build_temp_repo(tmp_path, issue_number=895)
    conventions = load_conventions(tmp_path)
    assert isinstance(conventions, Conventions)

    policy = PolicyHandle(coach_module=coach_core, conventions=conventions)
    assert policy.coach_module is coach_core
    assert policy.conventions is conventions

    params = dataclasses.fields(PolicyHandle)
    names = {f.name for f in params}
    assert names == {"coach_module", "conventions"}
    # Frozen: mutation must raise.
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.conventions = conventions  # type: ignore[misc]


def test_supporting_run_types_are_reachable_from_the_train_layer():
    from atdd.train.runner_iface import (  # noqa: F401
        RunId,
        RunState,
        RunStatus,
        RunSummary,
        TrainEvent,
        WaveResult,
    )


def test_runner_iface_imports_nothing_forbidden_by_section_3_3():
    """The train layer MUST NOT import atdd.cli or atdd.observer (§3.3)."""
    src = (
        Path(atdd.__file__).resolve().parent / "train" / "runner_iface.py"
    )
    tree = ast.parse(src.read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(n.name for n in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for forbidden in ("atdd.cli", "atdd.observer"):
        assert not any(
            imp == forbidden or imp.startswith(forbidden + ".") for imp in imported
        ), f"runner_iface imports forbidden {forbidden!r}"
