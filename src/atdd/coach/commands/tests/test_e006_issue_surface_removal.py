# URN: test:coach-verb-split:coach-verb-split:E006-UNIT-001-issue-surface-removal
# Acceptance: acc:coach-verb-split:E006-UNIT-001-issue-surface-removed-engines-and-verbs-survive
# Acceptance: acc:coach-verb-split:E006-INTEGRATION-001-every-removed-form-has-a-working-equivalent
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""C5b (#1309) — the ENDGAME of umbrella #1303: the `atdd issue` CLI surface is
DELETED and every reference to it is repointed.

What these tests prove, and what they deliberately do not:

  * The `issue` subparser and the whole `elif args.command == "issue":` dispatch
    block are GONE, replaced by a fail-loud pre-parse removal guard so the user
    gets a message naming the replacement instead of argparse's bare
    "invalid choice: 'issue'".
  * `issue.py` survives UNTOUCHED as a pure-engine module. It never held any CLI
    glue (no argparse, no `args`-taking function), so deleting the CLI removes
    CALLERS, never engines. IssueManager is still reached by `atdd list`,
    `atdd update`, `atdd manifest backfill` and four coach_verbs drop-ins.
  * Every removed `atdd issue <form>` has a working `atdd coach` / `atdd author`
    equivalent that reaches the SAME delegate. C1-C5a built those homes; this
    issue only deletes the shims, so parity is proven by construction and these
    tests pin it.

They do NOT re-test the engines — each has its own suite. They test that the
surface is gone and that nothing that depended on it broke.

HERMETIC BY CONSTRUCTION (feedback_transition_tests_must_be_hermetic): temp cwd +
temp ATDD_CONTROL_ROOT, every delegate stubbed with a recording spy. No real
issue/branch/store/manifest is read or mutated and no live `gh`/`git` runs. The
#1304 incident archived a real issue by testing on it — never route a real
number through an unstubbed engine.
"""
from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]

# A sentinel exit code distinct from 0/1/2 so a delegated call is unambiguous.
_SENTINEL_RC = 7
_FAKE_ISSUE = 424242
_FAKE_BRANCH = "refactor/never-a-real-branch-e006"


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Isolate cwd + control root so any leaked store/manifest write is contained."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


# =============================================================================
# AC-UNIT-001 — the surface is removed; the engines and verbs survive
# =============================================================================
class TestIssueSurfaceRemoved:
    """`atdd issue` is no longer a subcommand, and it fails loud rather than
    silently succeeding or emitting a bare argparse error."""

    def test_issue_is_not_a_registered_subparser(self):
        """The `issue` subparser is deleted from cli.py.

        Read as a SOURCE fact via the same regex the C2 validator uses, so this
        cannot be satisfied by a subparser that merely hides itself from --help.
        """
        from atdd.coach.validators.test_fix_hint_completeness import (
            build_subcommand_registry,
        )

        subcommands = build_subcommand_registry()
        assert subcommands, "subcommand registry must not be empty (regex drift?)"
        assert "issue" not in subcommands, (
            "`atdd issue` must be removed in 4.0.0; found it still registered "
            "as a top-level subparser"
        )
        # Sanity: the replacements the guard names really are registered.
        assert "coach" in subcommands
        assert "author" in subcommands

    def test_removed_command_is_declared_with_a_replacement_message(self):
        """cli.py declares `issue` as removed and names its replacements."""
        import atdd.cli as cli

        assert hasattr(cli, "REMOVED_COMMANDS"), (
            "cli.py must declare REMOVED_COMMANDS so the guard is data, not a "
            "hard-coded branch"
        )
        assert "issue" in cli.REMOVED_COMMANDS
        msg = cli.REMOVED_COMMANDS["issue"]
        assert "4.0.0" in msg
        assert "atdd coach" in msg
        assert "atdd author issue" in msg

    @pytest.mark.parametrize(
        "argv",
        [
            ["atdd", "issue"],
            ["atdd", "issue", "open"],
            ["atdd", "issue", str(_FAKE_ISSUE)],
            ["atdd", "issue", str(_FAKE_ISSUE), "--status", "RED"],
            ["atdd", "issue", "reconcile"],
            ["atdd", "issue", "is-registered", _FAKE_BRANCH],
        ],
    )
    def test_invoking_atdd_issue_exits_non_zero_naming_the_replacement(
        self, argv, capsys, hermetic
    ):
        """Every old form fails loud with OUR message, not argparse's."""
        import atdd.cli as cli

        with patch("sys.argv", argv):
            rc = cli.main()

        assert rc != 0, f"`{' '.join(argv)}` must exit non-zero after removal"
        err = capsys.readouterr().err
        assert "atdd coach" in err
        assert "atdd author issue" in err
        assert "4.0.0" in err
        # The guard must run BEFORE argparse, so the user never sees this:
        assert "invalid choice" not in err

    def test_engines_still_import_from_the_pure_engine_module(self):
        """issue.py stays put; the CLI removal must not touch it."""
        mod = importlib.import_module("atdd.coach.commands.issue")
        for symbol in (
            "IssueManager",
            "IssueBodyChecker",
            "IssueBodyComplianceError",
            "dup_check_before_file",
        ):
            assert hasattr(mod, symbol), f"engine {symbol} vanished from issue.py"

    def test_every_coach_verb_still_resolves(self):
        """The ten verbs the shims delegated to are all still discoverable."""
        from atdd.coach.commands import coach_verbs

        discovered = coach_verbs.discover()
        for verb in (
            "transition",
            "reconcile",
            "issues",
            "sync-labels",
            "issue-review",
            "is-registered",
            "check",
            "close-wmbt",
            "sync-wmbts",
            "enter",
        ):
            assert verb in discovered, f"coach verb `{verb}` no longer resolves"
            assert callable(discovered[verb])


# =============================================================================
# AC-INTEGRATION-001 — each removed form has a working equivalent
# =============================================================================
class TestReplacementsReachTheSameDelegate:
    """Each canonical replacement reaches the delegate the removed form used."""

    def _run_coach(self, argv):
        from atdd.coach.commands import coach_verbs

        verb = coach_verbs.resolve_verb(argv[0])
        assert verb is not None, f"verb {argv[0]!r} did not resolve"
        return verb(argv[1:])

    def test_transition_verb_is_the_issue_transition_entry_point(self):
        """`atdd coach transition` re-exports issue_transition.run verbatim.

        The drop-in does `from ...issue_transition import run`, so the verb IS
        the engine entry point — identity is the parity fact, not a spy call.
        """
        from atdd.coach.commands import coach_verbs, issue_transition

        assert coach_verbs.resolve_verb("transition") is issue_transition.run

    def test_reconcile_reaches_issue_manager_reconcile(self, hermetic):
        manager = MagicMock()
        manager.reconcile.return_value = _SENTINEL_RC
        with patch("atdd.coach.commands.issue.IssueManager", return_value=manager):
            rc = self._run_coach(["reconcile"])
        assert rc == _SENTINEL_RC
        manager.reconcile.assert_called_once()

    @pytest.mark.parametrize("registered,expected_rc", [(True, 0), (False, 1)])
    def test_is_registered_reaches_branch_is_registered(
        self, registered, expected_rc, hermetic
    ):
        """The verb maps the engine's truthiness to the gate's 0/1 exit code."""
        manager = MagicMock()
        manager.branch_is_registered.return_value = registered
        with patch("atdd.coach.commands.issue.IssueManager", return_value=manager):
            rc = self._run_coach(["is-registered", _FAKE_BRANCH])
        assert rc == expected_rc
        manager.branch_is_registered.assert_called_once_with(_FAKE_BRANCH)

    def test_sync_wmbts_reaches_sync_wmbts(self, hermetic):
        manager = MagicMock()
        manager.sync_wmbts.return_value = 0
        with patch("atdd.coach.commands.issue.IssueManager", return_value=manager):
            rc = self._run_coach(["sync-wmbts", str(_FAKE_ISSUE)])
        assert rc == 0
        manager.sync_wmbts.assert_called_once_with(_FAKE_ISSUE)

    def test_check_reaches_issue_lifecycle_check(self, hermetic):
        with patch(
            "atdd.coach.commands.issue_lifecycle.IssueLifecycle.check",
            return_value=_SENTINEL_RC,
        ) as spy:
            rc = self._run_coach(["check", str(_FAKE_ISSUE)])
        assert rc == _SENTINEL_RC
        assert spy.call_count == 1

    def test_close_wmbt_reaches_issue_lifecycle_close_wmbt(self, hermetic):
        with patch(
            "atdd.coach.commands.issue_lifecycle.IssueLifecycle.close_wmbt",
            return_value=_SENTINEL_RC,
        ) as spy:
            rc = self._run_coach(["close-wmbt", str(_FAKE_ISSUE), "E006"])
        assert rc == _SENTINEL_RC
        assert spy.call_count == 1


# =============================================================================
# AC-INTEGRATION-001 — the ported `atdd author issue --dry-run`
# =============================================================================
class TestAuthorIssueDryRun:
    """The one orphaned capability: render + validate + print, ZERO writes.

    `atdd author issue` publishes store-first, and its `--check PATH` only
    validates an existing file — neither covers `atdd issue <slug> --dry-run`.
    """

    def _run_author(self, argv):
        from atdd.planner.commands import author

        return author.run(argv)

    def test_dry_run_prints_body_and_writes_nothing(self, hermetic, capsys):
        with patch(
            "atdd.planner.commands.author_publish.publish_issue"
        ) as publish_spy:
            rc = self._run_author(
                [
                    "issue",
                    "--title",
                    "refactor(atdd): E006 dry run",
                    "--slug",
                    "e006-dry-run",
                    "--dry-run",
                ]
            )

        assert rc == 0, "a schema-valid dry-run body must exit 0"
        # dry-run must NOT publish to the store
        publish_spy.assert_not_called()
        out = capsys.readouterr().out
        assert "# " in out, "dry-run must print the rendered body on stdout"

    def test_dry_run_reports_schema_violations_and_exits_non_zero(
        self, hermetic, capsys
    ):
        with patch(
            "atdd.planner.commands.author.validate_issue_body",
            return_value=["missing ## Context"],
        ), patch("atdd.planner.commands.author_publish.publish_issue") as publish_spy:
            rc = self._run_author(
                ["issue", "--title", "bad", "--slug", "e006-bad", "--dry-run"]
            )

        assert rc != 0, "a non-validating dry-run body must exit non-zero"
        publish_spy.assert_not_called()
        err = capsys.readouterr().err
        assert "missing ## Context" in err
