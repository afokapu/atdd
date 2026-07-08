# URN: test:coach-verb-split:coach-verb-split:E003-INTEGRATION-001-coach-issues-read-extraction
# Acceptance: acc:coach-verb-split:E003-UNIT-001-issues-verb-auto-discovery
# Acceptance: acc:coach-verb-split:E003-INTEGRATION-001-coach-issues-delegates-identically
# WMBT: wmbt:coach-verb-split:E003
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""C3 (#1307) — `atdd coach issues` read-verb extraction parity (list + show/enter).

DELEGATION-ONLY: the read logic is NOT reimplemented — `issue_read.run` imports
and calls the existing `IssueManager.open_issues` (list) and
`IssueLifecycle.enter` (show/enter). These tests prove the new verb DELEGATES to
that unchanged logic and that the deprecated `atdd issue open` / `atdd issue <N>`
forms warn on stderr and delegate to the new verb.

HERMETIC BY CONSTRUCTION: every test runs with a temp cwd + temp
ATDD_CONTROL_ROOT and a THROWAWAY issue number (never a live issue), and stubs
every real-IO delegation seam (`IssueManager.open_issues`,
`IssueLifecycle.enter`, and `issue_read.run` for the shim tests) with recording
spies. No test lists, shows, enters, or mutates a real issue — the #1304
incident that archived a real issue by testing on it must not recur.

Behavior parity proved (mirrors the old `atdd issue open` / `atdd issue <N>` paths):
  1. `atdd coach issues` / `atdd coach issues open` route through the
     auto-discovery dispatch to `issue_read.run`, which reaches
     `IssueManager.open_issues` with the same (label, limit, assignee) args the
     old `atdd issue open` used.
  2. `atdd coach issues <N>` reaches `IssueLifecycle.enter(N)` — the show/enter
     path.
  3. The deprecated `atdd issue open` and `atdd issue <N>` still work: each
     warns on stderr (naming `atdd coach issues`) and delegates to the new verb
     entry point.
  4. The pattern is copyable: the coach_verbs package auto-discovers the
     `issues` drop-in with zero shared edits.
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


# ---------------------------------------------------------------------------
# 1. The pattern: auto-discovery resolves the `issues` verb with zero shared edits
# ---------------------------------------------------------------------------
class TestCoachIssuesVerbAutoDiscovery:
    def test_resolve_verb_finds_issues_dropin(self):
        from atdd.coach.commands.coach_verbs import discover, resolve_verb
        from atdd.coach.commands.issue_read import run as canonical_run

        assert resolve_verb("issues") is canonical_run
        assert discover().get("issues") is canonical_run

    def test_resolve_verb_returns_none_for_unknown_and_numeric(self):
        from atdd.coach.commands.coach_verbs import resolve_verb

        assert resolve_verb("nope") is None
        # A leading issue number must NOT resolve as a verb (it falls through to
        # the coach state-machine path).
        assert resolve_verb("1307") is None


# ---------------------------------------------------------------------------
# 2. Parity: the verb delegates the list identically (→ IssueManager.open_issues)
# ---------------------------------------------------------------------------
class TestCoachIssuesListDelegatesIdentically:
    def test_run_cli_routes_issues_open_to_open_issues(self, hermetic):
        """run_cli(['issues','open']) reaches IssueManager.open_issues with the
        same default args the old `atdd issue open` did, rc 0."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        open_spy = MagicMock(return_value=0)
        with patch.object(IssueManager, "open_issues", open_spy):
            rc = coach.run_cli(["issues", "open"])

        assert rc == 0
        open_spy.assert_called_once()
        _, kwargs = open_spy.call_args
        assert kwargs == {"label": None, "limit": 30, "assignee": None}

    def test_run_cli_issues_bare_lists(self, hermetic):
        """Bare `atdd coach issues` (no target) lists open issues, identical to
        `atdd coach issues open`."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        open_spy = MagicMock(return_value=0)
        with patch.object(IssueManager, "open_issues", open_spy):
            rc = coach.run_cli(["issues"])

        assert rc == 0
        open_spy.assert_called_once()
        _, kwargs = open_spy.call_args
        assert kwargs == {"label": None, "limit": 30, "assignee": None}

    def test_run_cli_issues_open_forwards_filters(self, hermetic):
        """--label / --limit / --assignee reach open_issues unchanged."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        open_spy = MagicMock(return_value=0)
        with patch.object(IssueManager, "open_issues", open_spy):
            rc = coach.run_cli(
                ["issues", "open", "--label", "bug", "--limit", "5", "--assignee", "octocat"]
            )

        assert rc == 0
        _, kwargs = open_spy.call_args
        assert kwargs == {"label": "bug", "limit": 5, "assignee": "octocat"}


# ---------------------------------------------------------------------------
# 3. Parity: the verb delegates show/enter identically (→ IssueLifecycle.enter)
# ---------------------------------------------------------------------------
class TestCoachIssuesEnterDelegatesIdentically:
    def test_run_cli_routes_issues_number_to_enter(self, hermetic):
        """run_cli(['issues', N]) reaches IssueLifecycle.enter(N) — the
        show/enter path — with the same argument the old `atdd issue <N>` did."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle

        enter_spy = MagicMock(return_value=0)
        with patch.object(IssueLifecycle, "enter", enter_spy):
            rc = coach.run_cli(["issues", str(_FAKE_ISSUE)])

        assert rc == 0
        enter_spy.assert_called_once()
        args, _ = enter_spy.call_args
        assert args == (_FAKE_ISSUE,)


# ---------------------------------------------------------------------------
# 4. Deprecated shims: `atdd issue open` / `atdd issue <N>` warn + delegate
# ---------------------------------------------------------------------------
class TestDeprecatedIssueReadShims:
    def test_issue_open_warns_and_delegates(self, hermetic, capsys, monkeypatch):
        import atdd.cli as cli
        import atdd.coach.commands.issue_read as ir

        monkeypatch.setattr("sys.argv", ["atdd", "issue", "open"])
        # Patch the delegate so NO real list I/O can occur even if wiring drifts.
        delegate_spy = MagicMock(return_value=0)
        with patch.object(ir, "run", delegate_spy):
            rc = cli.main()

        assert rc == 0
        delegate_spy.assert_called_once_with(["open"])
        err = capsys.readouterr().err
        assert "deprecated" in err.lower()
        assert "atdd coach issues" in err

    def test_issue_open_filters_forwarded_through_shim(self, hermetic, monkeypatch):
        import atdd.cli as cli
        import atdd.coach.commands.issue_read as ir

        monkeypatch.setattr(
            "sys.argv",
            ["atdd", "issue", "open", "--label", "bug", "--limit", "5", "--assignee", "octocat"],
        )
        delegate_spy = MagicMock(return_value=0)
        with patch.object(ir, "run", delegate_spy):
            rc = cli.main()

        assert rc == 0
        delegate_spy.assert_called_once_with(
            ["open", "--label", "bug", "--limit", "5", "--assignee", "octocat"]
        )

    def test_issue_enter_warns_and_delegates(self, hermetic, capsys, monkeypatch):
        import atdd.cli as cli
        import atdd.coach.commands.issue_read as ir

        monkeypatch.setattr("sys.argv", ["atdd", "issue", str(_FAKE_ISSUE)])
        delegate_spy = MagicMock(return_value=0)
        with patch.object(ir, "run", delegate_spy):
            rc = cli.main()

        assert rc == 0
        delegate_spy.assert_called_once_with([str(_FAKE_ISSUE)])
        err = capsys.readouterr().err
        assert "deprecated" in err.lower()
        assert "atdd coach issues" in err
