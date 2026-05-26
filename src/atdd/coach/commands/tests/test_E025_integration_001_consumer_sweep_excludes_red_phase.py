# URN: test:govern-lifecycle:consumer-validator-scope-gate:E025-INTEGRATION-001
# Acceptance: acc:govern-lifecycle:E025-INTEGRATION-001-consumer-repo-sweep-excludes-custom-themes-tests
# WMBT: wmbt:govern-lifecycle:E025
# Phase: GREEN
# Layer: integration
"""E025-INTEGRATION-001 — Consumer repo sweep does not collect Phase:RED tests.

Simulates the pre-push hook invocation from a consumer (non-ATDD-source) repo:
  atdd validate planner --local --skip-api

The planner validators include test_custom_themes.py and
test_custom_themes_schema.py, both marked Phase:RED and @pytest.mark.platform.
In a consumer context, TestRunner.run_tests() must inject 'not platform' so
those files are skipped — fixing the v3.81.1 regression (#846).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.platform]


_IS_SOURCE_REPO_TARGET = "atdd.coach.commands.test_runner.is_atdd_source_repo"


def test_consumer_planner_sweep_skips_custom_themes_tests(tmp_path, monkeypatch):
    """
    AC-INTEGRATION-001: TestRunner in consumer context with skip_api mode
    does not collect test_custom_themes*.py from the planner validators.

    This replicates the exact invocation path of the pre-push hook:
      split=False (--skip-api sets this in cli.py:2001)
      markers=["not github_api"]
      local=True

    The test captures the pytest command built by TestRunner and asserts that
    'not platform' is present in the marker expression — which is what prevents
    the offending files from being collected.
    """
    from atdd.coach.commands.test_runner import TestRunner

    captured_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr(_IS_SOURCE_REPO_TARGET, lambda: False)
    monkeypatch.setattr("subprocess.run", fake_run)

    runner = TestRunner(repo_root=tmp_path)
    monkeypatch.setattr(
        runner,
        "_get_validator_dirs",
        lambda phase=None: ["/fake/atdd/planner/validators"],
    )

    rc = runner.run_tests(
        phase="planner",
        split=False,
        local=True,
        markers=["not github_api"],
    )

    assert rc == 0
    assert captured_cmds, "Expected at least one pytest invocation"

    all_m_values: list[str] = []
    for cmd in captured_cmds:
        for i, tok in enumerate(cmd):
            if tok == "-m" and i + 1 < len(cmd):
                all_m_values.append(cmd[i + 1])

    combined = " ".join(all_m_values)
    assert "not platform" in combined, (
        f"Consumer + --skip-api invocation must include 'not platform' in "
        f"marker expression so Phase:RED tests (test_custom_themes*.py) are "
        f"excluded. Got marker args: {all_m_values!r}\n"
        "This is the regression from v3.81.1 — every consumer push touching "
        "plan/ was blocked by RED tests designed to fail until custom-themes lands."
    )
    assert "not github_api" in combined, (
        f"--skip-api must still exclude github_api tests, got: {all_m_values!r}"
    )
