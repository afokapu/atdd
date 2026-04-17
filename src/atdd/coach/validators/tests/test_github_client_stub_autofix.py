"""
Meta-tests for the ``atdd validate coach --fix`` autofix path (#304 Phase 4).

Proves two properties:

1. Running the autofix on a file with a hand-rolled ``GitHubClient`` stub
   rewrites the class header to subclass the real ``GitHubClient`` and
   inserts the import when missing.
2. The autofix is idempotent — a second run against the already-fixed
   file produces zero edits.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands.autofix import _rewrite_file

pytestmark = [pytest.mark.coach]


def test_autofix_converts_plain_stub_to_subclass(tmp_path: Path):
    """A plain ``class _FakeGithubClient:`` becomes
    ``class _FakeGithubClient(GitHubClient):`` and the real import is
    added when not already present."""
    path = tmp_path / "test_offender.py"
    path.write_text(
        '"""fixture"""\n'
        "import pytest\n"
        "\n"
        "class _FakeGithubClient:\n"
        "    def list_sub_issues(self, n): return []\n",
        encoding="utf-8",
    )

    edits, msg = _rewrite_file(path)

    assert edits == 1
    rewritten = path.read_text(encoding="utf-8")
    assert "class _FakeGithubClient(GitHubClient):" in rewritten
    assert "from atdd.coach.github import GitHubClient" in rewritten
    assert msg is not None


def test_autofix_is_idempotent_on_second_run(tmp_path: Path):
    """Re-running the autofix against a fixed file produces no edits and
    no message, matching #304 Decision #5 (opt-in, non-destructive)."""
    path = tmp_path / "test_offender.py"
    path.write_text(
        '"""fixture"""\n'
        "import pytest\n"
        "\n"
        "class _FakeGithubClient:\n"
        "    def list_sub_issues(self, n): return []\n",
        encoding="utf-8",
    )

    _rewrite_file(path)
    edits_second, msg_second = _rewrite_file(path)

    assert edits_second == 0
    assert msg_second is None


def test_autofix_leaves_subclass_declarations_alone(tmp_path: Path):
    """A class already inheriting from ``GitHubClient`` is untouched —
    the autofix does not add redundant bases."""
    path = tmp_path / "test_subclass_ok.py"
    original = (
        '"""fixture"""\n'
        "from atdd.coach.github import GitHubClient\n"
        "\n"
        "class RealSubclassClient(GitHubClient):\n"
        "    def ping(self): return None\n"
    )
    path.write_text(original, encoding="utf-8")

    edits, _ = _rewrite_file(path)

    assert edits == 0
    assert path.read_text(encoding="utf-8") == original
