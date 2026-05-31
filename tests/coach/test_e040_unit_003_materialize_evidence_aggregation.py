# URN: test:govern-lifecycle:extract-workflow-persistence-and-events-schema:E040-UNIT-003-materialize-evidence-aggregation
# Acceptance: acc:govern-lifecycle:E040-UNIT-003-materialize-evidence-aggregation
"""Unit test for E040-UNIT-003 (docs/coach-decomposition.md §4.6, §4.10, §7.1).

``materialize_evidence(issue_number)`` aggregates the manifest + GitHub adapter +
validator reports + filesystem artifacts into a frozen ``Evidence`` whose
conventions_hash matches the active ``Conventions``, degrading to CI=NONE /
pr_state=None when the GitHub adapter is unavailable (§7.1).
"""
from __future__ import annotations

import dataclasses
import json

import pytest

from atdd.coach.core.types import CiState, Evidence, IssueType, Phase, ValidatorReport
from atdd.integrations.github.types import PrStateData
from atdd.train.persistence import JsonlPersistenceStore, load_conventions

from tests.coach._e040_helpers import build_temp_repo

pytestmark = pytest.mark.atdd_validator


class _FakeGitHub:
    """Injected GitHub evidence source returning known data for the issue."""

    def __init__(self, *, raises: bool = False):
        self._raises = raises
        self._pr = PrStateData(
            number=999,
            state="OPEN",
            mergeable="MERGEABLE",
            merge_state="CLEAN",
            head_sha="deadbeef",
        )

    def read_phase(self, issue: int):
        if self._raises:
            raise RuntimeError("gh down")
        return "GREEN"

    def read_pr_state(self, issue: int):
        if self._raises:
            raise RuntimeError("gh down")
        return self._pr

    def read_ci_state(self, issue: int):
        if self._raises:
            raise RuntimeError("gh down")
        return "success"


def _seed_validator_report(store, run_id, repo):
    run_dir = repo / ".atdd" / "runtime" / "runs" / str(run_id)
    report = ValidatorReport(
        validator_id="some_validator",
        rule_id="planner.foo.bar",
        severity=3,
        disposition="warn-and-log",
        unsuppressed_count=1,
    )
    with (run_dir / "validator-reports.jsonl").open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(dataclasses.asdict(report)) + "\n")


def test_materialize_evidence_aggregates_all_sources(tmp_path):
    repo = build_temp_repo(tmp_path)
    conventions = load_conventions(repo)
    store = JsonlPersistenceStore(repo, github=_FakeGitHub())
    run_id = store.create_run(894, conventions=conventions)
    _seed_validator_report(store, run_id, repo)

    evidence = store.materialize_evidence(894)

    assert isinstance(evidence, Evidence)
    assert dataclasses.is_dataclass(evidence)
    # frozen
    with pytest.raises(dataclasses.FrozenInstanceError):
        evidence.issue_number = 1  # type: ignore[misc]

    assert evidence.issue_number == 894
    assert evidence.issue_type == IssueType.IMPLEMENTATION
    assert evidence.current_phase == Phase.GREEN
    assert evidence.train_id == "0001-self-compliance-validate"
    assert evidence.branch  # derived from the manifest slug
    assert evidence.conventions_hash == conventions.snapshot_hash

    # GitHub adapter mapped onto coach-core types.
    assert evidence.ci_state == CiState.SUCCESS
    assert evidence.pr_state is not None
    assert evidence.pr_state.number == 999
    assert evidence.pr_state.state == "OPEN"

    # Validator reports read back from validator-reports.jsonl.
    assert any(r.rule_id == "planner.foo.bar" for r in evidence.validator_reports)


def test_materialize_evidence_degrades_when_github_unavailable(tmp_path):
    repo = build_temp_repo(tmp_path)
    conventions = load_conventions(repo)
    store = JsonlPersistenceStore(repo, github=_FakeGitHub(raises=True))
    store.create_run(894, conventions=conventions)

    evidence = store.materialize_evidence(894)

    # §7.1: GitHub down → CI NONE, pr_state None, no exception propagated.
    assert evidence.ci_state == CiState.NONE
    assert evidence.pr_state is None
    # Manifest-derived fields still populated.
    assert evidence.issue_number == 894
    assert evidence.conventions_hash == conventions.snapshot_hash
