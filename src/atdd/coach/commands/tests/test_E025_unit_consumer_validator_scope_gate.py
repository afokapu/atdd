# URN: test:govern-lifecycle:consumer-validator-scope-gate:E025-UNIT-001
# URN: test:govern-lifecycle:consumer-validator-scope-gate:E025-UNIT-002
# URN: test:govern-lifecycle:consumer-validator-scope-gate:E025-UNIT-003
# Acceptance: acc:govern-lifecycle:E025-UNIT-001-platform-excluded-when-not-source-repo-no-split
# Acceptance: acc:govern-lifecycle:E025-UNIT-002-platform-excluded-when-not-source-repo-skip-api
# Acceptance: acc:govern-lifecycle:E025-UNIT-003-platform-tests-run-when-in-source-repo
# WMBT: wmbt:govern-lifecycle:E025
# Phase: RED
# Layer: unit
"""E025 — Consumer validator scope gate: platform-exclusion applies in all paths.

Root cause: TestRunner._run_split() adds 'and not platform' to the marker
expression only when is_atdd_source_repo() returns False. But when --skip-api
is passed, cli.py sets split=False so _run_split() is never called — the
platform exclusion is silently skipped and RED-phase toolkit tests (e.g.
test_custom_themes.py, test_custom_themes_schema.py) are collected in
consumer repos, blocking every push that touches plan/.

Fix: move the is_atdd_source_repo() → 'not platform' injection into
run_tests() before the split/no-split branch, so it applies regardless of
split mode.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODULE = "atdd.coach.commands.test_runner"
# test_runner.py does `from atdd.coach.utils.repo import is_atdd_source_repo`
# so we must patch the name in the test_runner module's namespace, not the
# origin module — otherwise the already-bound local reference isn't replaced.
_IS_SOURCE_REPO_TARGET = "atdd.coach.commands.test_runner.is_atdd_source_repo"


def _capture_pytest_cmds(
    monkeypatch,
    *,
    is_source: bool,
    split: bool,
    markers: list[str] | None = None,
    phase: str = "planner",
) -> list[list[str]]:
    """
    Instantiate TestRunner, patch is_atdd_source_repo + subprocess.run,
    call run_tests(), and return every pytest command list that was built.
    """
    from atdd.coach.commands.test_runner import TestRunner

    captured: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        captured.append(cmd)
        result = MagicMock()
        result.returncode = 0
        return result

    monkeypatch.setattr(_IS_SOURCE_REPO_TARGET, lambda: is_source)
    monkeypatch.setattr("subprocess.run", fake_run)

    runner = TestRunner(repo_root=Path("/fake/consumer-repo"))
    monkeypatch.setattr(
        runner,
        "_get_validator_dirs",
        lambda phase=None: ["/fake/atdd/planner/validators"],
    )

    runner.run_tests(
        phase=phase,
        split=split,
        local=True,
        markers=markers,
    )

    return captured


def _all_m_args(cmds: list[list[str]]) -> list[str]:
    """Extract every value that follows a '-m' flag across all captured commands."""
    result = []
    for cmd in cmds:
        for i, token in enumerate(cmd):
            if token == "-m" and i + 1 < len(cmd):
                result.append(cmd[i + 1])
    return result


# ---------------------------------------------------------------------------
# AC-UNIT-001: consumer + split=False → 'not platform' present
# ---------------------------------------------------------------------------


def test_platform_excluded_in_consumer_no_split_mode(monkeypatch):
    """
    AC-UNIT-001: run_tests(split=False) in a consumer repo must inject
    'not platform' into the marker expression.

    This is the regression that shipped in v3.81.1: _run_split() was the
    only caller of is_atdd_source_repo(), so split=False (the --skip-api
    path) silently omitted the consumer exclusion.
    """
    cmds = _capture_pytest_cmds(monkeypatch, is_source=False, split=False)

    m_args = _all_m_args(cmds)
    assert m_args, "Expected at least one -m argument in the pytest invocation"

    combined = " ".join(m_args)
    assert "not platform" in combined, (
        f"Consumer context + split=False must include 'not platform' in marker "
        f"expression, but got: {m_args!r}\n"
        "This means RED-phase toolkit tests (e.g. test_custom_themes.py) are "
        "being collected in consumer repos — every plan/ push gets blocked."
    )


# ---------------------------------------------------------------------------
# AC-UNIT-002: consumer + skip_api (→ split=False via CLI) → 'not platform'
# ---------------------------------------------------------------------------


def test_platform_excluded_in_consumer_with_skip_api_markers(monkeypatch):
    """
    AC-UNIT-002: When the CLI passes markers=['not github_api'] (the --skip-api
    path that sets split=False), consumer context must still inject 'not platform'.

    This replicates the exact invocation from the pre-push hook:
      atdd validate planner --local --skip-api
    which calls run_tests(markers=["not github_api"], split=False).
    """
    cmds = _capture_pytest_cmds(
        monkeypatch,
        is_source=False,
        split=False,
        markers=["not github_api"],
    )

    m_args = _all_m_args(cmds)
    combined = " ".join(m_args)

    assert "not platform" in combined, (
        f"--skip-api consumer invocation must include 'not platform', got: {m_args!r}"
    )
    assert "not github_api" in combined, (
        f"--skip-api must still include 'not github_api', got: {m_args!r}"
    )


# ---------------------------------------------------------------------------
# AC-UNIT-003: source repo → 'not platform' must NOT be present
# ---------------------------------------------------------------------------


def test_platform_tests_included_in_source_repo(monkeypatch):
    """
    AC-UNIT-003: Inside the ATDD source repo (is_atdd_source_repo() = True),
    platform-marked tests are the toolkit dogfood tests and MUST run.

    The 'not platform' exclusion must only apply to consumer contexts.
    """
    cmds = _capture_pytest_cmds(monkeypatch, is_source=True, split=False)

    m_args = _all_m_args(cmds)
    combined = " ".join(m_args)

    assert "not platform" not in combined, (
        f"Source repo context must NOT exclude 'platform' tests, "
        f"but 'not platform' found in: {m_args!r}"
    )


# ---------------------------------------------------------------------------
# AC-UNIT-003b: source repo with split=True also keeps platform tests
# ---------------------------------------------------------------------------


def test_platform_tests_included_in_source_repo_split_mode(monkeypatch):
    """
    Complementary to AC-UNIT-003: split=True in the source repo must also
    preserve platform tests (i.e., not add 'not platform').
    """
    cmds = _capture_pytest_cmds(monkeypatch, is_source=True, split=True)

    m_args = _all_m_args(cmds)
    combined = " ".join(m_args)

    assert "not platform" not in combined, (
        f"Source repo split=True must not exclude platform tests, got: {m_args!r}"
    )
