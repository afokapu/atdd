"""
Tests for pyproject.toml version-conflict auto-resolution in `atdd merge-cascade`.

Issue #365 Phase 3: when the cascade hits a pyproject.toml version-bump
conflict (the dominant cascade conflict), auto-resolve by picking the
higher PATCH version. Anything else conflicts → fail loud.

SPEC IDs: SPEC-COACH-ORCH-0010 (pyproject auto-resolve).
"""
from __future__ import annotations

import textwrap
from unittest.mock import patch

import pytest

from atdd.coach.commands.merge_cascade import (
    MergeResult,
    cascade,
    classify_conflict,
)
from atdd.coach.commands.merge_cascade_pyproject import (
    resolve_pyproject_version_conflict,
)

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# resolve_pyproject_version_conflict — pure helper
# ---------------------------------------------------------------------------


def test_resolves_simple_version_conflict_takes_higher():
    text = textwrap.dedent(
        """\
        [project]
        name = "atdd"
                version = "1.62.4"
        =======
        version = "1.62.2"
                description = "test"
        """
    )
    resolved = resolve_pyproject_version_conflict(text)
    assert resolved is not None
    assert 'version = "1.62.4"' in resolved
    assert "<<<<<<<" not in resolved
    assert "=======" not in resolved
    assert ">>>>>>>" not in resolved


def test_resolves_when_lower_is_first():
    text = textwrap.dedent(
        """\
                version = "1.62.1"
        =======
        version = "1.62.5"
                """
    )
    resolved = resolve_pyproject_version_conflict(text)
    assert resolved is not None
    assert 'version = "1.62.5"' in resolved


def test_returns_none_when_no_conflict():
    text = '[project]\nversion = "1.0.0"\n'
    assert resolve_pyproject_version_conflict(text) is None


def test_returns_none_when_conflict_is_not_version_only():
    """If the conflict block contains anything other than a version line, abort."""
    text = textwrap.dedent(
        """\
                version = "1.62.1"
        description = "old"
        =======
        version = "1.62.5"
        description = "new"
                """
    )
    assert resolve_pyproject_version_conflict(text) is None


def test_returns_none_when_versions_have_different_minor():
    """We only auto-resolve PATCH bumps; MINOR/MAJOR diffs need human review."""
    text = textwrap.dedent(
        """\
                version = "1.62.1"
        =======
        version = "1.63.0"
                """
    )
    assert resolve_pyproject_version_conflict(text) is None


def test_handles_multiple_conflict_blocks_only_if_all_version_only():
    """If there are multiple conflicts and they're all version-only, still resolves."""
    text = textwrap.dedent(
        """\
                version = "1.62.1"
        =======
        version = "1.62.3"
                [tool.poetry]
                version = "1.62.1"
        =======
        version = "1.62.3"
                """
    )
    resolved = resolve_pyproject_version_conflict(text)
    assert resolved is not None
    assert resolved.count('version = "1.62.3"') == 2


# ---------------------------------------------------------------------------
# classify_conflict — categorizes update-branch failures
# ---------------------------------------------------------------------------


def test_classify_conflict_detects_pyproject_only():
    stderr = "merge conflict in pyproject.toml"
    assert classify_conflict(stderr) == "pyproject_only"


def test_classify_conflict_detects_other_when_multiple_files():
    stderr = "merge conflict in pyproject.toml\nmerge conflict in src/foo.py"
    assert classify_conflict(stderr) == "other"


def test_classify_conflict_detects_other_for_non_pyproject():
    stderr = "merge conflict in src/foo.py"
    assert classify_conflict(stderr) == "other"


def test_classify_conflict_unknown_when_no_marker():
    stderr = "permission denied"
    assert classify_conflict(stderr) == "unknown"


# ---------------------------------------------------------------------------
# cascade integration — auto-resolve hook
# ---------------------------------------------------------------------------


def test_cascade_auto_resolves_pyproject_and_retries():
    """On pyproject-only conflict, cascade calls the resolver and retries update-branch."""
    call_log: list[str] = []

    def update_side_effect(pr):
        call_log.append(f"update:{pr}")
        # First call returns pyproject conflict; subsequent return merged
        if call_log.count(f"update:{pr}") == 1:
            return MergeResult(pr=pr, status="conflict", detail="merge conflict in pyproject.toml")
        return MergeResult(pr=pr, status="merged")

    def resolve_hook(pr):
        call_log.append(f"resolve:{pr}")
        return True  # resolved successfully

    with patch(
        "atdd.coach.commands.merge_cascade.update_branch",
        side_effect=update_side_effect,
    ), patch(
        "atdd.coach.commands.merge_cascade.attempt_pyproject_resolve",
        side_effect=resolve_hook,
    ), patch(
        "atdd.coach.commands.merge_cascade.wait_for_ci",
        return_value=MergeResult(pr=0, status="merged"),
    ), patch(
        "atdd.coach.commands.merge_cascade.merge_pr",
        return_value=MergeResult(pr=0, status="merged"),
    ):
        results = cascade([42], poll_interval=0, timeout=1, auto=True)
    assert [r.status for r in results] == ["merged"]
    assert call_log == ["update:42", "resolve:42", "update:42"]


def test_cascade_fails_loud_on_non_pyproject_conflict():
    from atdd.coach.commands.merge_cascade import MergeHalt

    def update_side_effect(pr):
        return MergeResult(pr=pr, status="conflict", detail="merge conflict in src/foo.py")

    with patch(
        "atdd.coach.commands.merge_cascade.update_branch",
        side_effect=update_side_effect,
    ), patch(
        "atdd.coach.commands.merge_cascade.attempt_pyproject_resolve",
    ) as resolve_mock, patch(
        "atdd.coach.commands.merge_cascade.wait_for_ci",
        return_value=MergeResult(pr=0, status="merged"),
    ), patch(
        "atdd.coach.commands.merge_cascade.merge_pr",
        return_value=MergeResult(pr=0, status="merged"),
    ):
        with pytest.raises(MergeHalt) as exc_info:
            cascade([42], poll_interval=0, timeout=1, auto=True)
    # Non-pyproject conflicts must NOT trigger auto-resolve
    resolve_mock.assert_not_called()
    assert "src/foo.py" in exc_info.value.result.detail


def test_cascade_halts_when_resolver_fails():
    from atdd.coach.commands.merge_cascade import MergeHalt

    def update_side_effect(pr):
        return MergeResult(pr=pr, status="conflict", detail="merge conflict in pyproject.toml")

    with patch(
        "atdd.coach.commands.merge_cascade.update_branch",
        side_effect=update_side_effect,
    ), patch(
        "atdd.coach.commands.merge_cascade.attempt_pyproject_resolve",
        return_value=False,
    ), patch(
        "atdd.coach.commands.merge_cascade.wait_for_ci",
        return_value=MergeResult(pr=0, status="merged"),
    ), patch(
        "atdd.coach.commands.merge_cascade.merge_pr",
        return_value=MergeResult(pr=0, status="merged"),
    ):
        with pytest.raises(MergeHalt) as exc_info:
            cascade([42], poll_interval=0, timeout=1, auto=True)
    assert exc_info.value.result.status == "conflict"
