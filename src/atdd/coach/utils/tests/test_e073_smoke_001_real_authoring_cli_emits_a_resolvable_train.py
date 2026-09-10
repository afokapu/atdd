# URN: test:govern-lifecycle:train-identity-resolves-across-vocabularies:E073-SMOKE-001-real-authoring-cli-emits-a-resolvable-train
# Acceptance: acc:govern-lifecycle:E073-SMOKE-001-real-authoring-cli-emits-a-resolvable-train
# WMBT: wmbt:govern-lifecycle:E073
# Phase: SMOKE
# Layer: integration
"""E073-SMOKE-001 — the real authoring CLI emits a train that resolves (#1890).

The UNIT tests read the default out of the source. This one runs `atdd author
issue --dry-run` as a subprocess and resolves the identity the CLI actually
rendered, because the defect was an operator-visible one: issues arrived carrying
a train the PLANNED gate would refuse, and nothing between authoring and that gate
said so.

`--dry-run` is the whole of the observation. A spike established that the
non-dry-run path resolves a live GitHub issue through `gh`, so it cannot be
exercised against a synthetic project at all — see
docs/spikes/1890-train-write-validation.md.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

import pytest

from atdd.coach.commands.issue import IssueManager
from atdd.coach.utils.train_identity import check_train_id

pytestmark = [pytest.mark.platform]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]


@pytest.fixture(scope="module")
def rendered_train() -> str:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    result = subprocess.run(
        [sys.executable, "-m", "atdd", "author", "issue",
         "--title", "E073 smoke probe", "--slug", "e073-smoke-probe", "--dry-run"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    match = re.search(r"\|\s*Train\s*\|\s*`([^`]+)`\s*\|", result.stdout)
    assert match, f"the CLI rendered no Train row:\n{result.stdout[:800]}"
    return match.group(1)


def test_the_rendered_train_resolves(rendered_train: str) -> None:
    declared = IssueManager._registered_train_ids(REPO_ROOT / "plan")
    assert declared, "no trains declared — this guard would pass vacuously"

    verdict = check_train_id(rendered_train, declared)
    assert verdict.resolves, (
        f"`atdd author issue` rendered train {rendered_train!r}, which "
        f"{verdict.detail.splitlines()[0]}\n"
        "An issue authored this way is refused at PLANNED."
    )


def test_the_rendered_train_is_canonical(rendered_train: str) -> None:
    """A shipped default that is legacy would extend the migration with every
    newly authored issue."""
    declared = IssueManager._registered_train_ids(REPO_ROOT / "plan")
    assert not check_train_id(rendered_train, declared).legacy_format, (
        f"the CLI defaults to the legacy spelling {rendered_train!r}"
    )


def test_the_dry_run_creates_nothing(rendered_train: str) -> None:
    """Named explicitly because this test runs against the real repository."""
    probe = REPO_ROOT / "plan" / "e073-smoke-probe.yaml"
    assert not probe.exists(), f"the dry run wrote {probe}"
