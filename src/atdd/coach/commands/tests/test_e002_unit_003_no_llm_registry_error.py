# URN: test:review-phase-boundaries:E002-UNIT-003-no-llm-registry-error
# Acceptance: acc:review-phase-boundaries:E002-UNIT-003-no-llm-registry-error
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: unit

"""E002-UNIT-003 — no LLM_REGISTRY entries yields a clear error, nonzero exit.

When judge.LLM_REGISTRY is empty, atdd coach review must print a human-
readable error mentioning 'no LLM clients configured' and a reference to
docs/MODELS.md, then exit nonzero without printing a traceback.
"""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


@pytest.fixture()
def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / ".atdd" / "runtime"
    root.mkdir(parents=True)
    return root


def test_no_llm_registry_exits_nonzero(runtime_root: Path, capsys) -> None:
    """Empty LLM_REGISTRY causes nonzero exit."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.coach_review import run_review

    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    try:
        with patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}):
            rc = run_review(["--commit", "deadbeef01234567"])
    finally:
        judge_mod.LLM_REGISTRY.update(original_registry)

    assert rc != 0


def test_no_llm_registry_prints_clear_message(runtime_root: Path, capsys) -> None:
    """Empty LLM_REGISTRY prints 'no LLM clients configured' message."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.coach_review import run_review

    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    try:
        with patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}):
            run_review(["--commit", "deadbeef01234567"])
    finally:
        judge_mod.LLM_REGISTRY.update(original_registry)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "no LLM clients configured" in combined
    assert "MODELS.md" in combined


def test_no_llm_registry_no_traceback(runtime_root: Path, capsys) -> None:
    """Empty LLM_REGISTRY does not produce a Python traceback on stdout/stderr."""
    from atdd.coach.commands import judge as judge_mod
    from atdd.coach.commands.coach_review import run_review

    original_registry = dict(judge_mod.LLM_REGISTRY)
    judge_mod.LLM_REGISTRY.clear()
    try:
        with patch.dict("os.environ", {"ATDD_RUNTIME_ROOT": str(runtime_root)}):
            run_review(["--commit", "deadbeef01234567"])
    finally:
        judge_mod.LLM_REGISTRY.update(original_registry)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "Traceback" not in combined
