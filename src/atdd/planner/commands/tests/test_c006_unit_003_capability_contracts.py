# URN: test:author-atdd-substrate:substrate-spine:C006-UNIT-003-capability-contracts
# Acceptance: acc:author-atdd-substrate:C006-UNIT-003-capability-contracts
# WMBT: wmbt:author-atdd-substrate:C006
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C006-UNIT-003 — a workspace declares typed CAPABILITIES; required fields are
validated from each capability's contract. A non-execution provider (isolation/scm)
needs no runner; an execution capability requires runtime; unknown domain/contract and
a malformed capability are refused."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_manifest import validate_workspace_manifest

_GIT_WORKTREE = {
    "kind": "workspace",
    "workspace_id": "atdd.workspace.git-worktree",
    "capabilities": [
        {"capability_id": "environment.git-worktree", "domain": "environment",
         "type": "isolated-worktree",
         "contract": "atdd.workspace.capability.environment.isolation.v1"},
        {"capability_id": "source_control.git-trailers", "domain": "source_control",
         "type": "commit-trailers",
         "contract": "atdd.workspace.capability.source-control.commit-trailers.v1", "vcs": "git"},
    ],
}
_PYTEST = {
    "kind": "workspace", "workspace_id": "atdd.workspace.python-pytest",
    "capabilities": [
        {"capability_id": "execution.pytest", "domain": "execution", "type": "test-runner",
         "contract": "atdd.workspace.capability.execution.command-runner.v1",
         "runtime": {"language": "python", "runner": "pytest", "command": "pytest"}},
    ],
}


def test_non_execution_provider_needs_no_runner():
    validate_workspace_manifest(_GIT_WORKTREE)   # isolation + scm, no runtime -> accepted


def test_execution_capability_accepted_with_runtime():
    validate_workspace_manifest(_PYTEST)


def test_execution_capability_without_runtime_refused():
    bad = {**_PYTEST, "capabilities": [{k: v for k, v in _PYTEST["capabilities"][0].items() if k != "runtime"}]}
    with pytest.raises(AuthorInputError) as exc:
        validate_workspace_manifest(bad)
    assert exc.value.field == "capabilities"


def test_unknown_domain_refused():
    bad = {"kind": "workspace", "workspace_id": "acme.workspace.x",
           "capabilities": [{"capability_id": "x", "domain": "bogus", "type": "t", "contract": "c"}]}
    with pytest.raises(AuthorInputError):
        validate_workspace_manifest(bad)


def test_unknown_contract_refused():
    bad = {"kind": "workspace", "workspace_id": "acme.workspace.x",
           "capabilities": [{"capability_id": "x", "domain": "environment", "type": "t",
                             "contract": "atdd.workspace.capability.environment.unknown.v9"}]}
    with pytest.raises(AuthorInputError):
        validate_workspace_manifest(bad)


def test_scm_commit_trailers_requires_git():
    bad = {"kind": "workspace", "workspace_id": "acme.workspace.x",
           "capabilities": [{"capability_id": "scm.x", "domain": "source_control", "type": "commit-trailers",
                             "contract": "atdd.workspace.capability.source-control.commit-trailers.v1"}]}
    with pytest.raises(AuthorInputError):
        validate_workspace_manifest(bad)


def test_workspace_with_no_capabilities_refused():
    with pytest.raises(AuthorInputError) as exc:
        validate_workspace_manifest({"kind": "workspace", "workspace_id": "acme.workspace.x"})
    assert exc.value.field == "capabilities"
