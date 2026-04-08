"""
Shared fixtures for tester tests.
"""
# Import all shared fixtures from coach via absolute import
from atdd.coach.validators.shared_fixtures import *  # noqa: F401,F403

import pytest
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root
from atdd.coder.baselines.ratchet import RatchetBaseline


def tester_baseline_path(repo_root: Path) -> Path:
    """Return the canonical baseline file path for tester validators."""
    return repo_root / ".atdd" / "baselines" / "tester.yaml"


@pytest.fixture(scope="module")
def ratchet_baseline() -> RatchetBaseline:
    """
    Ratchet baseline fixture for tester validators.

    Loads ``.atdd/baselines/tester.yaml`` from the target repo.
    Validators use it to assert that violation counts do not regress::

        def test_my_validator(ratchet_baseline):
            violations = analyze(repo)
            ratchet_baseline.assert_no_regression(
                validator_id="my_validator",
                current_count=len(violations),
                violations=violations,
            )
    """
    repo_root = find_repo_root()
    return RatchetBaseline(tester_baseline_path(repo_root))
