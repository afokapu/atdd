# URN: test:coach-verb-split:coach-verb-split:E003-SMOKE-001-real-read-in-temp-control-root
# Acceptance: acc:coach-verb-split:E003-SMOKE-001-real-read-in-temp-control-root
# WMBT: wmbt:coach-verb-split:E003
# Phase: SMOKE
# Harness: smoke
# Layer: integration
# Assertion: behavioral
"""E003-SMOKE-001 — live end-to-end read parity for `atdd coach issues`.

Exercises the REAL verb dispatch + REAL rendering (only the GitHub I/O seam is
stubbed) against a temp ``ATDD_CONTROL_ROOT`` with a throwaway issue number —
never a live issue (the #1304 incident that archived a real issue by testing on
it must not recur). Unlike the E003 INTEGRATION tests (which spy on the
delegation target to prove the CALL happens), this smoke runs the FULL render
path end-to-end and proves byte-for-byte output parity:

  - ``atdd coach issues [open]`` renders the open-issue list identically to the
    deprecated ``atdd issue open``.
  - ``atdd coach issues <N>`` renders the show/enter context identically to the
    deprecated ``atdd issue <N>``.
  - the deprecated shims emit their stderr deprecation notice while producing
    identical stdout (so the notice never pollutes the rendered payload).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]

# A number that is NOT any real GitHub issue — see the hermeticity note above.
_FAKE_ISSUE = 999003


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Isolate cwd + control root so any leaked read/list I/O is contained."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


_FAKE_OPEN_ISSUES = [
    {
        "number": _FAKE_ISSUE,
        "title": "throwaway read smoke",
        "labels": [{"name": "atdd-issue"}, {"name": "atdd:SMOKE"}],
        "createdAt": "2026-07-08T00:00:00Z",
    },
    {
        "number": _FAKE_ISSUE + 1,
        "title": "second throwaway",
        "labels": [{"name": "atdd-issue"}],
        "createdAt": "2026-07-08T00:00:00Z",
    },
]

# A TERMINAL-status issue so enter() takes the display-only print path and never
# attempts worktree/branch creation — keeping the smoke deterministic + offline.
_FAKE_TERMINAL_ISSUE = {
    "number": _FAKE_ISSUE,
    "title": "throwaway read smoke",
    "state": "CLOSED",
    "labels": [{"name": "atdd-issue"}, {"name": "atdd:COMPLETE"}],
    "body": "## Issue Metadata\n",
}


def _list_stub() -> MagicMock:
    client = MagicMock()
    client.list_open_issues.return_value = _FAKE_OPEN_ISSUES
    return client


class TestCoachIssuesReadSmokeParity:
    def test_list_renders_identically_via_new_verb_and_shim(
        self, hermetic, capsys, monkeypatch
    ):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager
        import atdd.cli as cli

        with patch.object(IssueManager, "_check_initialized", return_value=True), \
             patch.object(IssueManager, "_get_github_client", return_value=_list_stub()):
            # New verb: `atdd coach issues open`
            rc_new = coach.run_cli(["issues", "open"])
            out_new = capsys.readouterr().out

            # Deprecated shim: `atdd issue open`
            monkeypatch.setattr("sys.argv", ["atdd", "issue", "open"])
            rc_dep = cli.main()
            captured = capsys.readouterr()
            out_dep, err_dep = captured.out, captured.err

        assert rc_new == 0 and rc_dep == 0
        # A real render actually happened (not an empty/stubbed no-op).
        assert f"#{_FAKE_ISSUE}" in out_new
        assert "throwaway read smoke" in out_new
        # Byte-for-byte parity between the new verb and the deprecated shim.
        assert out_new == out_dep
        # The shim warns on stderr (never on stdout) and names the new verb.
        assert "deprecated" in err_dep.lower()
        assert "atdd coach issues" in err_dep

    def test_enter_renders_identically_via_new_verb_and_shim(
        self, hermetic, capsys, monkeypatch
    ):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        import atdd.cli as cli

        with patch.object(IssueLifecycle, "_fetch_issue", return_value=_FAKE_TERMINAL_ISSUE), \
             patch.object(IssueLifecycle, "_fetch_sub_issues", return_value=[]):
            # New verb: `atdd coach issues <N>`
            rc_new = coach.run_cli(["issues", str(_FAKE_ISSUE)])
            out_new = capsys.readouterr().out

            # Deprecated shim: `atdd issue <N>`
            monkeypatch.setattr("sys.argv", ["atdd", "issue", str(_FAKE_ISSUE)])
            rc_dep = cli.main()
            captured = capsys.readouterr()
            out_dep, err_dep = captured.out, captured.err

        assert rc_new == 0 and rc_dep == 0
        # A real context render actually happened for the throwaway issue.
        assert str(_FAKE_ISSUE) in out_new
        # Byte-for-byte parity between the new verb and the deprecated shim.
        assert out_new == out_dep
        # The shim warns on stderr (never on stdout) and names the new verb.
        assert "deprecated" in err_dep.lower()
        assert "atdd coach issues" in err_dep
