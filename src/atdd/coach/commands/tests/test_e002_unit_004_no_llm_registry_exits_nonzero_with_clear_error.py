# URN: test:review-phase-boundaries:review-phase-boundaries:E002-UNIT-004-no-llm-registry-exits-nonzero-with-clear-error
# Acceptance: acc:review-phase-boundaries:E002-UNIT-004-no-llm-registry-exits-nonzero-with-clear-error
# WMBT: wmbt:review-phase-boundaries:E002
# Phase: RED
# Layer: application
# Assertion: behavioral
"""E002-UNIT-004 — When no LLM clients are configured, `atdd coach review`
prints a clear error referencing docs/MODELS.md and exits nonzero without
crashing.

Given:
  - ADAPTER_REGISTRY (spawn.py) is empty (no spawn adapters registered).

When:
  - run_coach_review(commit="abc1234") is called with no LLM configured.

Then:
  - The command exits nonzero.
  - stderr/error output contains 'no LLM clients configured' and references
    docs/MODELS.md.
  - No reviewer agent directory is created.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


class TestNoLlmRegistry:
    def test_exits_nonzero_with_clear_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import coach_review
        from atdd.coach.commands import spawn as spawn_mod

        runtime_root = tmp_path / ".atdd" / "runtime"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", lambda pr: "abc1234")

        errors: list[str] = []
        monkeypatch.setattr(coach_review, "_print_err", lambda msg: errors.append(msg))
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)

        original_registry = dict(spawn_mod.ADAPTER_REGISTRY)
        spawn_mod.ADAPTER_REGISTRY.clear()
        try:
            rc = coach_review.run(commit="abc1234")
        finally:
            spawn_mod.ADAPTER_REGISTRY.update(original_registry)

        assert rc != 0, "expected nonzero exit when ADAPTER_REGISTRY is empty"
        combined = " ".join(errors).lower()
        assert "no llm clients configured" in combined, (
            f"expected 'no LLM clients configured' in error output, got: {errors}"
        )
        assert "docs/models.md" in combined or "docs/MODELS.md" in " ".join(errors), (
            f"expected docs/MODELS.md reference in error output, got: {errors}"
        )

    def test_no_agent_dir_created_when_no_llm(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from atdd.coach.commands import coach_review
        from atdd.coach.commands import spawn as spawn_mod

        runtime_root = tmp_path / ".atdd" / "runtime"
        monkeypatch.setenv("ATDD_RUNTIME_ROOT", str(runtime_root))
        monkeypatch.setattr(coach_review, "_resolve_pr_commit", lambda pr: "abc1234")
        monkeypatch.setattr(coach_review, "_print_err", lambda msg: None)
        monkeypatch.setattr(coach_review, "_print", lambda msg: None)

        original_registry = dict(spawn_mod.ADAPTER_REGISTRY)
        spawn_mod.ADAPTER_REGISTRY.clear()
        try:
            coach_review.run(commit="abc1234")
        finally:
            spawn_mod.ADAPTER_REGISTRY.update(original_registry)

        agents_dir = runtime_root / "agents"
        reviewer_dirs = list(agents_dir.iterdir()) if agents_dir.exists() else []
        assert reviewer_dirs == [], (
            f"expected no agent dirs created, got: {reviewer_dirs}"
        )
