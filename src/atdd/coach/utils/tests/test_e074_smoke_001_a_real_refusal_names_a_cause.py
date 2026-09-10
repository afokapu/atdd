# URN: test:govern-lifecycle:issue-fetch-separates-absent-from-unavailable:E074-SMOKE-001-a-real-refusal-names-a-cause
# Acceptance: acc:govern-lifecycle:E074-SMOKE-001-a-real-refusal-names-a-cause
# WMBT: wmbt:govern-lifecycle:E074
# Phase: SMOKE
# Layer: integration
"""E074-SMOKE-001 — a real refusal names its cause (#1895).

The UNIT tests stub `gh`. This one runs the installed CLI as a subprocess against
an issue number that genuinely does not exist, because the defect lived in what an
operator READ at a terminal: `atdd coach transition 1876 COMPLETE` refused with
"could not fetch issue #1876" while #1876 was open and fine.

Marked `github_api` — it makes one real API call and CI deselects it when no
credential is available. It asserts only on the SHAPE of the refusal, never on
rate-limit state, so it cannot itself become a test whose verdict tracks the
network.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.platform, pytest.mark.github_api]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[5]
ABSENT_ISSUE = 999999999


@pytest.fixture(scope="module")
def refusal() -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "atdd", "coach", "transition", str(ABSENT_ISSUE), "COMPLETE"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, env=env,
    )


def test_the_call_refuses(refusal) -> None:
    """Both an established absence and an unestablished verdict refuse; what
    differs is the sentence, not the exit code."""
    assert refusal.returncode != 0


def test_the_refusal_names_a_cause(refusal) -> None:
    blob = (refusal.stdout + refusal.stderr).lower()
    assert "could not fetch issue" not in blob, (
        "the generic message is back: it asserts nothing about WHY and reads as a "
        "statement about the repository"
    )
    assert any(
        phrase in blob
        for phrase in ("does not exist", "could not be read", "rate limit", "not installed")
    ), f"the refusal names no cause:\n{refusal.stdout[-600:]}\n{refusal.stderr[-600:]}"


def test_the_refusal_carries_a_remedy(refusal) -> None:
    blob = refusal.stdout + refusal.stderr
    assert any(
        phrase in blob
        for phrase in ("Check the number", "atdd coach issues open", "gh auth", "rate_limit", "Retry")
    ), f"the refusal offers nothing to do next:\n{blob[-600:]}"
