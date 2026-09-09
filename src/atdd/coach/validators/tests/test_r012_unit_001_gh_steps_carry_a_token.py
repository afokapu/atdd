# URN: test:govern-lifecycle:govern-lifecycle:R012-UNIT-001-every-step-that-shells-out-to-gh-is-given-a-token
# Acceptance: acc:govern-lifecycle:R012-UNIT-001-every-step-that-shells-out-to-gh-is-given-a-token
# WMBT: wmbt:govern-lifecycle:R012
# Phase: RED
# Layer: application
"""R012-UNIT-001 — a step that reaches `gh` must be handed the token it reads.

TWO assertions, because the requirement arrives two different ways and one check
cannot honestly cover both.

The first is the broad class: a step whose own command text invokes `gh`. That is
statically visible and carries no ambiguity.

The second is the case that actually bit. The release drain's command text never
mentions `gh` at all — it runs a Python entry point, and the `gh release create`
lives inside the release worker that entry point loads. The credential requirement
travels with the CALLEE, and no amount of reading the step's text will reveal it.
So the callee is named explicitly.

A first draft of this test tried to infer the second case from markers like
"drain" and "release_worker" appearing in the command text. It flagged three
steps, two of them wrongly — a `git clone` of a public repository and an `echo` of
a warning. A check that tells you to add a GitHub token to an `echo` is worse than
no check: it trains the reader to add credentials where they do not belong.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

_TOKEN_VARS = {"GH_TOKEN", "GITHUB_TOKEN"}

# Entry points known to shell out to `gh` from inside the process they start.
# Text analysis cannot see through these, so they are named.
_KNOWN_GH_CALLEES = ("drain_version_decided", "release_worker", "release_entrypoint")


def _env_names(*blocks) -> set[str]:
    names: set[str] = set()
    for block in blocks:
        if isinstance(block, dict):
            names |= {str(k) for k in block}
    return names


def _steps(repo_root: Path):
    """Yield (workflow, job_name, step, credentials-visible-to-that-step)."""
    for path in sorted((repo_root / ".github" / "workflows").glob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:  # pragma: no cover
            pytest.fail(f"{path.name} is not parseable YAML: {exc}")
        workflow_env = _env_names(doc.get("env"))
        for job_name, job in (doc.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            job_env = _env_names(job.get("env")) | workflow_env
            for step in job.get("steps") or []:
                if isinstance(step, dict):
                    yield path, job_name, step, _env_names(step.get("env")) | job_env


@pytest.mark.coder
@pytest.mark.platform
def test_a_step_invoking_gh_directly_is_given_a_token():
    """The broad class, visible in the step's own text."""
    if not is_atdd_source_repo():
        pytest.skip("reads this repository's own committed workflows")

    offenders = [
        f"{path.name}::{job}::{step.get('name') or '<unnamed>'}"
        for path, job, step, available in _steps(Path(find_repo_root()))
        if "gh " in str(step.get("run") or "") and not (available & _TOKEN_VARS)
    ]

    assert not offenders, (
        "these steps invoke the gh CLI with neither GH_TOKEN nor GITHUB_TOKEN in "
        f"scope, and gh refuses without one: {offenders}"
    )


@pytest.mark.coder
@pytest.mark.platform
def test_a_step_running_a_known_gh_callee_is_given_a_token():
    """The case that bit: `gh` is called by the worker, not by the step.

    This is the defect R012 exists for. The step's command text mentions no `gh`,
    so the assertion above cannot see it, and the failure only appears at runtime
    as gh's own missing-token error.
    """
    if not is_atdd_source_repo():
        pytest.skip("reads this repository's own committed workflows")

    offenders = [
        f"{path.name}::{job}::{step.get('name') or '<unnamed>'}"
        for path, job, step, available in _steps(Path(find_repo_root()))
        if any(callee in str(step.get("run") or "") for callee in _KNOWN_GH_CALLEES)
        and not (available & _TOKEN_VARS)
    ]

    assert not offenders, (
        "these steps execute an entry point that shells out to gh, but supply no "
        f"token, so the call fails at runtime with gh's own error: {offenders}"
    )
