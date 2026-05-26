# URN: test:govern-lifecycle:consumer-validator-scope-gate:E025-SMOKE-001-consumer-validator-rejects-toolkit-only-tests
# Acceptance: acc:govern-lifecycle:E025-SMOKE-001-consumer-validator-rejects-toolkit-only-tests
# WMBT: wmbt:govern-lifecycle:E025
# Phase: GREEN
# Layer: backend.integration
"""
AC-SMOKE-001: in a clean consumer fixture, atdd validate planner --local --skip-api
does not collect or fail on any Phase:RED toolkit-internal test.

This is the end-to-end confirmation of the E025 scope gate fix (#846). It simulates
the exact pre-push hook invocation path (split=False, markers=["not github_api"]) from
a consumer repo and asserts that 'not platform' is injected — which prevents
test_custom_themes.py and test_custom_themes_schema.py from being collected.

Prior to the fix, this invocation path omitted 'not platform' because _run_split()
was not called (--skip-api sets split=False in cli.py:2001).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.platform]

_IS_SOURCE_REPO_TARGET = "atdd.coach.commands.test_runner.is_atdd_source_repo"


def test_consumer_skip_api_sweep_injects_not_platform(tmp_path: Path, monkeypatch):
    """
    AC-SMOKE-001: pre-push hook equivalent path (split=False, markers=['not github_api'])
    from a consumer repo must include 'not platform' so Phase:RED toolkit tests are
    excluded and consumer pushes are not blocked.
    """
    from atdd.coach.commands.test_runner import TestRunner

    captured_cmds: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(list(cmd))
        result = MagicMock()
        result.returncode = 0
        return result

    # Simulate consumer context: is_atdd_source_repo() returns False
    monkeypatch.setattr(_IS_SOURCE_REPO_TARGET, lambda: False)
    monkeypatch.setattr("subprocess.run", fake_run)

    runner = TestRunner(repo_root=tmp_path)
    monkeypatch.setattr(
        runner,
        "_get_validator_dirs",
        lambda phase=None: ["/installed/atdd/planner/validators"],
    )

    # Replicate exact CLI path from pre-push hook:
    #   atdd validate planner --local --skip-api
    # which calls run_tests(split=False, markers=["not github_api"], local=True)
    rc = runner.run_tests(
        phase="planner",
        split=False,
        local=True,
        markers=["not github_api"],
    )

    assert rc == 0, f"Expected exit 0, got {rc}"
    assert captured_cmds, "No pytest command was built — TestRunner did not invoke pytest"

    # Every captured command must include 'not platform'
    for cmd in captured_cmds:
        m_values = [
            cmd[i + 1]
            for i, tok in enumerate(cmd)
            if tok == "-m" and i + 1 < len(cmd)
        ]
        combined = " ".join(m_values)

        assert "not platform" in combined, (
            f"Consumer + --skip-api (split=False) must include 'not platform' "
            f"so test_custom_themes*.py (Phase:RED, @pytest.mark.platform) are excluded.\n"
            f"  Marker args: {m_values!r}\n"
            f"  Full cmd: {cmd}\n"
            "This is the v3.81.1 regression: _run_split() was the only caller of "
            "is_atdd_source_repo(); --skip-api bypassed it. Fix: inject 'not platform' "
            "in run_tests() before the split branch (E025 scope gate)."
        )
        assert "not github_api" in combined, (
            f"--skip-api must still filter github_api tests, got: {m_values!r}"
        )
