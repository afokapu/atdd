# URN: test:govern-lifecycle:phase-aware-coverage:E081-UNIT-001-coverage-validators-respect-pre-red-phase
# Acceptance: acc:govern-lifecycle:E081-UNIT-001-coverage-validators-respect-pre-red-phase
# WMBT: wmbt:govern-lifecycle:E081
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E081-UNIT-001 — train coverage is demanded from RED onward, not before.

RED: `train_completeness`, `train_e2e_existence` and `train_route_smoke_coverage`
demand `e2e/{train_id}/` from every registered train with no reference to the
owning issue's phase — `grep -c 'phase\\|PLANNED\\|RED'` returns 0 across all
three. A train authored at PLANNED is therefore failed for not yet carrying the
tests RED exists to write, and because their violations are bare strings with no
`rule_id`, the disposition gate treats them as strict-by-default: no ratchet and
no `# atdd:suppress` escape either (#1920).

The decision is unit-tested through `coverage_is_due`, which is the seam the
three validators share; `test_e081_integration_001` drives the validators
themselves end-to-end.
"""
from __future__ import annotations

import pytest
import yaml

from atdd.tester.validators._acceptance_walker import (
    coverage_is_due,
    owning_train_phase,
)

# Toolkit self-tests: the `platform` marker is what keeps them out of a
# consumer repo's validator run.
pytestmark = [pytest.mark.platform]

TRAIN_ID = "train:issue-lifecycle:brand-new"

PRE_TEST_PHASES = ["INIT", "PLANNED"]
TEST_DUE_PHASES = ["RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"]


@pytest.fixture
def repo(tmp_path):
    """A consumer repo registering one train, with no e2e/ — RED has not run."""
    (tmp_path / ".atdd" / "state").mkdir(parents=True)
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\nthemes:\n  0: commons\n", encoding="utf-8"
    )
    (tmp_path / "plan" / "_trains" / "issue-lifecycle").mkdir(parents=True)
    (tmp_path / "plan" / "_trains.yaml").write_text(yaml.safe_dump({
        "trains": {"issue-lifecycle": {"nominal": [{
            "train_id": TRAIN_ID, "description": "authored before RED",
            "path": "plan/_trains/issue-lifecycle/brand-new.yaml",
            "wagons": ["some-wagon"], "category": "nominal",
        }]}}
    }), encoding="utf-8")
    return tmp_path


def _bind_work_item(repo, phase, *, train=TRAIN_ID, slug="lab-work-item"):
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=repo))
    try:
        create_work_item(conn, slug, state=phase,
                         data={"title": "the owning issue", "train": train})
    finally:
        conn.close()


@pytest.mark.parametrize("phase", PRE_TEST_PHASES)
def test_coverage_is_not_due_before_red(repo, phase):
    _bind_work_item(repo, phase)
    assert owning_train_phase(repo, TRAIN_ID) == phase
    assert coverage_is_due(repo, TRAIN_ID) is False


@pytest.mark.parametrize("phase", TEST_DUE_PHASES)
def test_coverage_is_due_from_red_onward(repo, phase):
    _bind_work_item(repo, phase)
    assert coverage_is_due(repo, TRAIN_ID) is True


def test_an_unmapped_train_fails_closed(repo):
    """No work item maps the train — demand the coverage rather than skip it.

    An untracked train must never become a way to switch the check off.
    """
    assert owning_train_phase(repo, TRAIN_ID) is None
    assert coverage_is_due(repo, TRAIN_ID) is True


def test_an_escape_phase_fails_closed(repo):
    """BLOCKED and OBSOLETE are off the linear order — not 'before RED'."""
    _bind_work_item(repo, "BLOCKED")
    assert coverage_is_due(repo, TRAIN_ID) is True


def test_the_most_advanced_owner_decides(repo):
    """Two issues on one train: coverage is due once ANY of them has reached RED.

    Mirrors `owning_issue_phase` — a train counts as still pre-test only when
    every owning work item is pre-test.
    """
    _bind_work_item(repo, "PLANNED", slug="planned-owner")
    _bind_work_item(repo, "GREEN", slug="green-owner")
    assert owning_train_phase(repo, TRAIN_ID) == "GREEN"
    assert coverage_is_due(repo, TRAIN_ID) is True


def test_a_work_item_bound_to_another_train_does_not_leak(repo):
    """Only work items naming THIS train may relax it."""
    _bind_work_item(repo, "PLANNED", train="train:issue-lifecycle:someone-else")
    assert owning_train_phase(repo, TRAIN_ID) is None
    assert coverage_is_due(repo, TRAIN_ID) is True
