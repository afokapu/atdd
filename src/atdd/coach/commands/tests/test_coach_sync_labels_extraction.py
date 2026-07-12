# URN: test:coach-verb-split:coach-verb-split:E004-INTEGRATION-001-coach-sync-labels-extraction
# Acceptance: acc:coach-verb-split:E004-UNIT-001-sync-labels-verb-auto-discovery
# Acceptance: acc:coach-verb-split:E004-INTEGRATION-001-coach-sync-labels-delegates-identically
# WMBT: wmbt:coach-verb-split:E004
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""C4 (#1308) — `atdd coach sync-labels` extraction parity via the #1304
coach-verb auto-discovery pattern (child of umbrella #1303).

DELEGATION-ONLY: this verb re-implements nothing. It parses argv and delegates
to the unchanged `IssueManager.sync_labels` / `sync_labels_all` (the label
re-derivation + GitHub delta) and `cli._print_sync_labels_delta` (the
presentation). These tests prove the DELEGATION, not the derivation — the
derivation has its own suite (test_sync_labels.py).

HERMETIC BY CONSTRUCTION: every test runs with a temp cwd + temp
ATDD_CONTROL_ROOT and a THROWAWAY issue number (never a live issue — the #1304
incident archived a real issue by testing on it), and stubs the GitHub-touching
`IssueManager.sync_labels` / `sync_labels_all` at the class level. No test may
mutate labels on a real issue.

Behavior parity proved (mirrors the old `atdd issue sync-labels` path):
  1. Auto-discovery resolves the verb drop-in with zero shared edits.
  2. `atdd coach sync-labels <N>` reaches `IssueManager.sync_labels(N, dry_run)`
     with the same args the old `atdd issue sync-labels <N>` did.
  3. `--all` reaches `sync_labels_all`, not the single-issue path.
  4. `--dry-run` forwards to the delegate.
  5. A missing number/`--all` returns 1 without any GitHub call.
  6. The deprecated `atdd issue sync-labels` warns on stderr and delegates to
     the new verb entry point with the reconstructed argv.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]

# A number that is NOT any real GitHub issue — see the hermeticity note above.
_FAKE_ISSUE = 999002


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Isolate cwd + control root so any leaked GitHub/store write is contained."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# 1. The pattern: auto-discovery resolves the verb with zero shared edits
# ---------------------------------------------------------------------------
class TestCoachSyncLabelsAutoDiscovery:
    def test_resolve_verb_finds_sync_labels_dropin(self):
        from atdd.coach.commands.coach_verbs import discover, resolve_verb
        from atdd.coach.commands.coach_verbs.sync_labels import run as canonical_run

        # The hyphenated CLI token maps to the underscore module and resolves
        # to its run() — zero edits to run_cli / cli.py / any registry list.
        assert resolve_verb("sync-labels") is canonical_run
        assert discover().get("sync-labels") is canonical_run

    def test_resolve_verb_returns_none_for_unknown_and_numeric(self):
        from atdd.coach.commands.coach_verbs import resolve_verb

        assert resolve_verb("nope") is None
        # A leading issue number must NOT resolve as a verb (it falls through to
        # the coach state-machine path).
        assert resolve_verb("1308") is None


# ---------------------------------------------------------------------------
# 2. Parity: the verb delegates to IssueManager.sync_labels identically
# ---------------------------------------------------------------------------
class TestCoachSyncLabelsDelegatesIdentically:
    def test_run_cli_routes_single_issue_to_sync_labels(self, hermetic):
        """run_cli(['sync-labels', N]) reaches IssueManager.sync_labels(N,
        dry_run=False) — the same call the old `atdd issue sync-labels N`
        made — and never touches the --all path."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        sync_spy = MagicMock(return_value={"to_add": [], "to_remove": []})
        all_spy = MagicMock(return_value=[])
        with patch.object(IssueManager, "sync_labels", sync_spy), \
             patch.object(IssueManager, "sync_labels_all", all_spy):
            rc = coach.run_cli(["sync-labels", str(_FAKE_ISSUE)])

        assert rc == 0
        sync_spy.assert_called_once_with(_FAKE_ISSUE, dry_run=False)
        all_spy.assert_not_called()

    def test_run_cli_forwards_dry_run(self, hermetic):
        """--dry-run reaches sync_labels as dry_run=True."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        sync_spy = MagicMock(return_value={"to_add": [], "to_remove": []})
        with patch.object(IssueManager, "sync_labels", sync_spy):
            rc = coach.run_cli(["sync-labels", str(_FAKE_ISSUE), "--dry-run"])

        assert rc == 0
        sync_spy.assert_called_once_with(_FAKE_ISSUE, dry_run=True)

    def test_run_cli_all_routes_to_sync_labels_all(self, hermetic):
        """--all reaches sync_labels_all(dry_run=...) and never the
        single-issue path."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        sync_spy = MagicMock(return_value={"to_add": [], "to_remove": []})
        all_spy = MagicMock(return_value=[])
        with patch.object(IssueManager, "sync_labels", sync_spy), \
             patch.object(IssueManager, "sync_labels_all", all_spy):
            rc = coach.run_cli(["sync-labels", "--all", "--dry-run"])

        assert rc == 0
        all_spy.assert_called_once_with(dry_run=True)
        sync_spy.assert_not_called()

    def test_run_cli_missing_number_and_all_errors_without_github(self, hermetic):
        """No <N> and no --all → rc 1, and NO GitHub-touching delegate is
        called (parity with the old dispatch's guard)."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        sync_spy = MagicMock(return_value={"to_add": [], "to_remove": []})
        all_spy = MagicMock(return_value=[])
        with patch.object(IssueManager, "sync_labels", sync_spy), \
             patch.object(IssueManager, "sync_labels_all", all_spy):
            rc = coach.run_cli(["sync-labels"])

        assert rc == 1
        sync_spy.assert_not_called()
        all_spy.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Deprecated shim: `atdd issue sync-labels` warns on stderr + delegates
# ---------------------------------------------------------------------------
