# URN: test:train:0001-self-compliance-validate:E2E-001-train-renders-content-smoke
# Train: train:0001-self-compliance-validate
# Phase: SMOKE
# Layer: assembly
# Runtime: python
# Smoke: true
# Assertion: behavioral
# Purpose: End-to-end smoke for the train-render validator (#335) — real subprocess, real config, real ratchet.
"""
Smoke for src/atdd/tester/validators/test_train_renders_content.py.

Two scenarios exercise the assembled stack (no mocks of the validator):

1. ``test_validator_skips_when_opt_in_off``: with the toolkit-self default
   config (``train_renders_content.enabled`` absent), the orchestration test
   inside the validator must collect and skip cleanly via ``atdd validate``.

2. ``test_invoker_handles_missing_entrypoint``: with a real Python interpreter,
   instantiate the integration adapter against a tmp repo root that has no
   ``.atdd/harness/mount-train.mjs`` and assert it surfaces TESTER-RENDER-003
   instead of raising — proving the #357 silent-swallow contract holds end
   to end.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.tester.validators.test_train_renders_content import (
    HarnessInvoker,
    TrainRenderAnalyzer,
    RULE_HARNESS_ERROR,
)


REPO_ROOT = find_repo_root()


def _run_pytest(target: str, *extra: str, timeout: int = 90) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "pytest", target, "-v", "--no-header", *extra]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=timeout,
    )


class TestTrainRendersContentSmoke:
    """Smoke: real subprocess + real validator + real config."""

    def test_validator_skips_when_opt_in_off(self):
        """Toolkit-self has no .atdd/config.yaml → train_renders_content;
        the orchestration test must skip rather than fail."""
        target = (
            "src/atdd/tester/validators/test_train_renders_content.py"
            "::test_repo_train_renders_content"
        )
        result = _run_pytest(target)
        assert result.returncode == 0, (
            f"pytest exit {result.returncode}\n"
            f"STDOUT:\n{result.stdout[-800:]}\n"
            f"STDERR:\n{result.stderr[-400:]}"
        )
        assert "skipped" in result.stdout.lower(), (
            "expected SKIPPED outcome when opt-in is off; got:\n"
            f"{result.stdout[-800:]}"
        )

    def test_invoker_surfaces_missing_entrypoint_as_violation(self, tmp_path: Path):
        """With no harness installed, invoke() must return a result whose
        error is set, and the analyzer must turn that into a single
        TESTER-RENDER-003 — never raise, never bare try/except."""
        invoker = HarnessInvoker(repo_root=tmp_path)
        result = invoker.invoke("synthetic-train-id")

        assert result.error is not None
        assert "harness" in result.error.lower()

        analyzer = TrainRenderAnalyzer(repo_root=tmp_path)
        violations = analyzer.classify(result)
        assert len(violations) == 1
        assert violations[0].rule_id == RULE_HARNESS_ERROR
        assert violations[0].severity == 3

    def test_analyzer_fixture_pipeline_matches_recorded_outputs(self):
        """Read each fixture JSON, classify, and assert the rule_id set
        matches the fixture name. Exercises the full deserialize →
        classify path through the public APIs."""
        from atdd.tester.validators.test_train_renders_content import (
            FIXTURE_ROOT,
            TrainRenderHarnessResult,
        )

        expected = {
            "pass": set(),
            "fail_empty": {"TESTER-RENDER-001"},
            "fail_stub": {"TESTER-RENDER-002"},
            "harness_error": {"TESTER-RENDER-003"},
        }
        analyzer = TrainRenderAnalyzer(REPO_ROOT)
        for name, expected_ids in expected.items():
            payload = json.loads(
                (FIXTURE_ROOT / name / "harness_output.json").read_text(encoding="utf-8")
            )
            result = TrainRenderHarnessResult.from_dict(payload)
            ids = {v.rule_id for v in analyzer.classify(result)}
            assert ids == expected_ids, f"fixture {name!r}: expected {expected_ids}, got {ids}"
