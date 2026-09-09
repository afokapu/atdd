# URN: test:govern-lifecycle:govern-lifecycle:R012-UNIT-001-every-step-that-shells-out-to-gh-is-given-a-token
# Acceptance: acc:govern-lifecycle:R012-UNIT-001-every-step-that-shells-out-to-gh-is-given-a-token
# WMBT: wmbt:govern-lifecycle:R012
# Phase: RED
# Layer: application
"""R012-UNIT-001 — a step that reaches `gh` must be handed the token it reads.

The broad, statically visible class: a step whose own command text invokes `gh`.
Every such step must have the credential gh reads in scope.

This passes today and is a regression guard. The defect R012 exists for is NOT
visible here — the release drain's command text never mentions `gh`, because the
call lives inside the worker it loads — and that case is asserted against the real
committed workflow in SMOKE-001, where the callee can be named.

An earlier draft tried to infer the callee from markers in the command text. It
flagged three steps, two wrongly: a `git clone` of a public repository and an
`echo` of a warning. A check that tells you to put a GitHub token on an `echo` is
worse than no check — it teaches the reader to spray credentials.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root, is_atdd_source_repo

_TOKEN_VARS = {"GH_TOKEN", "GITHUB_TOKEN"}

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
