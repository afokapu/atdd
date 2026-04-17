"""
Meta-tests for the GitHubClient hand-rolled stub validator.

These tests exercise the validator's pure helpers against in-memory fixture
files instead of running against the real project tree. They verify the
three properties that matter:

1. A hand-rolled class named ``FakeGitHubClient`` (no bases) is flagged.
2. A class that explicitly subclasses ``GitHubClient`` passes silently.
3. A file that uses ``create_autospec(GitHubClient, instance=True)`` without
   declaring any ``GitHubClient``-named class passes silently.

Covers validator-side of #304 (fix(atdd): Github Client Mock Drift).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_github_client_mock_spec import (
    _find_hand_rolled_stubs,
    _scan,
)


pytestmark = [pytest.mark.coach]


def _write(tmp_path: Path, filename: str, body: str) -> Path:
    path = tmp_path / filename
    path.write_text(body, encoding="utf-8")
    return path


def test_flags_hand_rolled_plain_class_named_githubclient(tmp_path):
    """A class whose identifier contains ``GitHubClient`` with no bases
    declared must be reported as an offense, regardless of leading
    underscores or case."""
    path = _write(
        tmp_path,
        "test_offender.py",
        "class _FakeGithubClient:\n"
        "    def list_sub_issues(self, n): return []\n",
    )

    offenses = _find_hand_rolled_stubs(path)

    assert len(offenses) == 1
    assert offenses[0].class_name == "_FakeGithubClient"
    assert "hand-rolled" in offenses[0].reason


def test_passes_class_that_subclasses_real_githubclient(tmp_path):
    """A class explicitly declared as ``class X(GitHubClient):`` is allowed
    — subclass inherits the real method surface."""
    path = _write(
        tmp_path,
        "test_subclass_ok.py",
        "from atdd.coach.github import GitHubClient\n"
        "class RealSubclassClient(GitHubClient):\n"
        "    def __init__(self): pass\n",
    )

    offenses = _find_hand_rolled_stubs(path)

    assert offenses == []


def test_passes_file_using_create_autospec_only(tmp_path):
    """A test file that constructs its doubles via ``create_autospec`` and
    declares no ``GitHubClient``-named class is silent — the validator only
    flags class declarations, never usage sites."""
    path = _write(
        tmp_path,
        "test_autospec_only.py",
        "from unittest.mock import create_autospec\n"
        "from atdd.coach.github import GitHubClient\n"
        "def test_x():\n"
        "    client = create_autospec(GitHubClient, instance=True)\n"
        "    client.get_sub_issues.return_value = []\n",
    )

    offenses = _find_hand_rolled_stubs(path)

    assert offenses == []


def test_scan_walks_subtree_and_reports_per_file(tmp_path):
    """Given a subtree containing one offender and one clean file, ``_scan``
    returns exactly one offense keyed on the offending file path."""
    _write(
        tmp_path,
        "test_clean.py",
        "from unittest.mock import create_autospec\n"
        "from atdd.coach.github import GitHubClient\n"
        "def test_ok():\n"
        "    create_autospec(GitHubClient, instance=True)\n",
    )
    offender = _write(
        tmp_path,
        "test_offender.py",
        "class StubGitHubClient:\n"
        "    def list_sub_issues(self, n): return []\n",
    )

    offenses = _scan(tmp_path)

    assert len(offenses) == 1
    assert offenses[0].path == offender
    assert offenses[0].class_name == "StubGitHubClient"


def test_scan_ignores_classes_without_githubclient_in_name(tmp_path):
    """Classes unrelated to GitHubClient (e.g. fixture helpers, data
    classes) are never reported. The validator is narrowly scoped to
    GitHubClient drift detection (Decision #6)."""
    _write(
        tmp_path,
        "test_unrelated.py",
        "class FakeManifest:\n"
        "    pass\n"
        "class _HelperBuilder:\n"
        "    def build(self): return None\n",
    )

    offenses = _scan(tmp_path)

    assert offenses == []
