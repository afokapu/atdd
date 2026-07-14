# URN: test:govern-lifecycle:ship-package-data-and-consumer-ci:C009-UNIT-001-workflow-declares-a-wheel-installing-consumer-job
# Acceptance: acc:govern-lifecycle:C009-UNIT-001-workflow-declares-a-wheel-installing-consumer-job
# WMBT: wmbt:govern-lifecycle:C009
# Phase: GREEN
# Layer: backend.presentation
# Assertion: structural
"""C009-UNIT-001 — CI declares a job that installs the WHEEL, and gates on it.

Every existing job runs `PYTHONPATH=src python3 -m pytest src/atdd/<phase>/validators/`.
That puts the working tree on the import path, so `atdd.__file__` always resolves
into the checkout, every file exists by definition, and `package-data` is never
consulted. The wheel is built only at publish time — after merge. No PR could go
red for a packaging defect, which is why #663 sat open from 3.47.0 until a
downstream user reported it.

Three things must hold, because there are three ways to add a job that looks like
an oracle and isn't:
  * it installs the BUILT WHEEL (not `PYTHONPATH=src`, which is the blindness)
  * it runs from a synthetic consumer dir (no `src/atdd/` to shadow the package)
  * it is in the `validate-gate` fan-in (a job that reports but cannot block is
    a notification, not a gate)
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.coach]

_JOB = "validate-consumer"


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


@pytest.fixture()
def workflow() -> dict:
    path = _repo_root() / ".github" / "workflows" / "atdd-validate.yml"
    assert path.is_file(), f"{path} does not exist"
    return yaml.safe_load(path.read_text())


def _job_script(job: dict) -> str:
    """Every `run:` line in the job, concatenated."""
    return "\n".join(
        step.get("run", "") for step in job.get("steps", []) if isinstance(step, dict)
    )


def test_c009_unit_001_workflow_declares_the_consumer_job(workflow: dict):
    assert _JOB in workflow["jobs"], (
        f"`{_JOB}` is not declared in atdd-validate.yml. Without it no CI job ever "
        f"installs the package, and package-data is never exercised."
    )


def test_c009_unit_001_consumer_job_installs_the_built_wheel(workflow: dict):
    script = _job_script(workflow["jobs"][_JOB])

    assert "-m build" in script, (
        f"`{_JOB}` never builds the wheel — it cannot exercise package-data without one"
    )
    assert "pip install" in script and ".whl" in script, (
        f"`{_JOB}` never `pip install`s the built wheel artifact"
    )
    assert "PYTHONPATH=src" not in script, (
        f"`{_JOB}` puts the source tree on the import path. That is exactly the "
        f"blindness this job exists to remove: with `src/` importable, every data "
        f"file resolves from the checkout and a wheel that omits it still passes."
    )


def test_c009_unit_001_consumer_job_runs_from_a_synthetic_consumer_repo(workflow: dict):
    script = _job_script(workflow["jobs"][_JOB])

    assert "git init" in script, (
        f"`{_JOB}` does not create a synthetic consumer repo — the shipped validators "
        f"must be exercised from a directory with no `src/atdd/`, the way a consumer "
        f"runs them"
    )


def test_c009_unit_001_consumer_job_is_a_required_check(workflow: dict):
    gate = workflow["jobs"].get("validate-gate")
    assert gate is not None, "validate-gate fan-in is missing from the workflow"

    assert _JOB in gate.get("needs", []), (
        f"`{_JOB}` is not in the `validate-gate` fan-in, so a packaging regression "
        f"would be reported and merged anyway. A job that cannot block is not a gate."
    )
    assert _JOB in _job_script(gate), (
        f"`validate-gate` does not check `{_JOB}`'s result in its status loop, so the "
        f"job's failure would not fail the gate"
    )
