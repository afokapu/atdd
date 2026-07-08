# URN: test:coach-verb-split:coach-verb-split:E002-INTEGRATION-001-coach-reconcile-extraction
# Acceptance: acc:coach-verb-split:E002-UNIT-001-reconcile-verb-auto-discovery
# Acceptance: acc:coach-verb-split:E002-INTEGRATION-001-coach-reconcile-delegates-identically
# Acceptance: acc:coach-verb-split:E002-SMOKE-001-real-reconcile-in-temp-control-root
# WMBT: wmbt:coach-verb-split:E002
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""C2 (#1305) — `atdd coach reconcile` extraction parity + the auto-discovery
CLI-registration pattern (copies C1/#1304, umbrella #1303).

DELEGATION-ONLY: the new verb does NOT reimplement reconcile — it delegates to
the existing ``IssueManager.reconcile()`` (the backfill-from-GitHub engine with
the merged E054 fixes). These tests prove the wiring, never the engine (which is
covered by its own suite + the E054 tests).

HERMETIC BY CONSTRUCTION: every test runs with a temp cwd + temp
ATDD_CONTROL_ROOT, and the reconcile engine is ALWAYS stubbed with a recording
spy (unit/integration) or driven to its manifest-not-found guard in an isolated
tmp cwd (smoke) — so ``gh issue list`` is NEVER called against live GitHub and no
real issue/manifest is ever mutated. (The #1304 incident archived a real issue by
testing on it — see feedback_transition_tests_must_be_hermetic.)

Behavior parity proved (mirrors the old `atdd issue reconcile` path):
  1. `atdd coach reconcile` routes through the auto-discovery dispatch to the
     reconcile drop-in's ``run``, which reaches ``IssueManager.reconcile()`` once
     and returns its exit code — the DELEGATION guarantee.
  2. The deprecated `atdd issue reconcile` still works: it warns on stderr naming
     `atdd coach reconcile` and delegates to the new verb (reaching the same
     engine), returning its exit code.
  3. The pattern is copyable: the coach_verbs package auto-discovers the reconcile
     drop-in with zero shared edits.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]

# A sentinel exit code distinct from 0/1 so a delegated call is unambiguous.
_SENTINEL_RC = 7


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Isolate cwd + control root so any leaked store/manifest write is contained."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# 1. The pattern: auto-discovery resolves the verb with zero shared edits
#    (acc:coach-verb-split:E002-UNIT-001-reconcile-verb-auto-discovery)
# ---------------------------------------------------------------------------
class TestCoachReconcileVerbAutoDiscovery:
    def test_resolve_verb_finds_reconcile_dropin(self):
        from atdd.coach.commands.coach_verbs import discover, resolve_verb
        from atdd.coach.commands.coach_verbs.reconcile import run as canonical_run

        assert resolve_verb("reconcile") is canonical_run
        assert discover().get("reconcile") is canonical_run

    def test_reconcile_module_declares_the_verb_token(self):
        from atdd.coach.commands.coach_verbs import reconcile

        assert reconcile.VERB == "reconcile"
        assert callable(reconcile.run)

    def test_resolve_verb_returns_none_for_unknown_and_numeric(self):
        from atdd.coach.commands.coach_verbs import resolve_verb

        assert resolve_verb("nope") is None
        # A leading issue number must NOT resolve as a verb (it falls through to
        # the coach state-machine path).
        assert resolve_verb("1305") is None


# ---------------------------------------------------------------------------
# 2. Parity: `atdd coach reconcile` delegates to IssueManager.reconcile()
#    (acc:coach-verb-split:E002-INTEGRATION-001, part 1)
# ---------------------------------------------------------------------------
class TestCoachReconcileDelegatesToIssueManager:
    def test_run_cli_reconcile_reaches_issuemanager_reconcile_once(self, hermetic):
        """coach.run_cli(['reconcile']) reaches IssueManager.reconcile() exactly
        once (no args after the verb) and returns the exit code it produced.

        The engine is spied, so no live `gh issue list` runs."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        reconcile_spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(IssueManager, "reconcile", reconcile_spy):
            rc = coach.run_cli(["reconcile"])

        assert rc == _SENTINEL_RC, "the verb must return reconcile()'s exit code"
        reconcile_spy.assert_called_once_with()

    def test_verb_run_delegates_to_reconcile_and_does_not_reimplement(self, hermetic):
        """Calling the drop-in's run([]) directly reaches IssueManager.reconcile()
        once — proving the verb is a thin delegator, not a reimplementation."""
        from atdd.coach.commands.coach_verbs.reconcile import run as reconcile_run
        from atdd.coach.commands.issue import IssueManager

        reconcile_spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(IssueManager, "reconcile", reconcile_spy):
            rc = reconcile_run([])

        assert rc == _SENTINEL_RC
        reconcile_spy.assert_called_once_with()


# ---------------------------------------------------------------------------
# 3. Deprecated shim: `atdd issue reconcile` warns on stderr + delegates
#    (acc:coach-verb-split:E002-INTEGRATION-001, part 2)
# ---------------------------------------------------------------------------
class TestDeprecatedIssueReconcileShim:
    def test_issue_reconcile_warns_and_reaches_same_engine(
        self, hermetic, capsys, monkeypatch
    ):
        """The deprecated path prints a one-line stderr deprecation notice naming
        `atdd coach reconcile`, and reaches the SAME IssueManager.reconcile()
        engine exactly once, returning its exit code."""
        import atdd.cli as cli
        from atdd.coach.commands.issue import IssueManager

        monkeypatch.setattr("sys.argv", ["atdd", "issue", "reconcile"])
        reconcile_spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(IssueManager, "reconcile", reconcile_spy):
            rc = cli.main()

        assert rc == _SENTINEL_RC
        reconcile_spy.assert_called_once_with()
        err = capsys.readouterr().err
        assert "deprecated" in err.lower(), "shim must warn on stderr"
        assert "atdd coach reconcile" in err, "shim must name the canonical verb"

    def test_issue_reconcile_delegates_through_the_coach_verb(
        self, hermetic, monkeypatch
    ):
        """The shim delegates to the NEW verb (not a duplicated reconcile call):
        it invokes coach_verbs.reconcile.run with the post-verb argv ([])."""
        import atdd.cli as cli
        import atdd.coach.commands.coach_verbs.reconcile as reconcile_mod

        monkeypatch.setattr("sys.argv", ["atdd", "issue", "reconcile"])
        # Patch the delegate so NO real reconcile can occur even if wiring drifts.
        delegate_spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(reconcile_mod, "run", delegate_spy):
            rc = cli.main()

        assert rc == _SENTINEL_RC
        delegate_spy.assert_called_once_with([])


# ---------------------------------------------------------------------------
# 4. SMOKE: real `atdd coach reconcile` in a temp control root reaches the real
#    engine's manifest guard, never touching live GitHub
#    (acc:coach-verb-split:E002-SMOKE-001-real-reconcile-in-temp-control-root)
# ---------------------------------------------------------------------------
@pytest.mark.smoke
class TestReconcileSmokeInTempControlRoot:
    def _run(self, argv, cwd):
        import os
        import subprocess
        import sys
        from pathlib import Path

        import atdd

        # Run the SAME atdd the test process imports (the code under test), not
        # whatever happens to be installed: derive an ABSOLUTE source root from
        # the imported package and pin it on PYTHONPATH. A relative PYTHONPATH=src
        # would not resolve from the tmp cwd and would fall back to the installed
        # build. Pin ATDD_CONTROL_ROOT to the tmp dir so the run is fully isolated.
        src_root = str(Path(atdd.__file__).resolve().parent.parent)
        env = dict(os.environ)
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = src_root + (os.pathsep + existing if existing else "")
        env["ATDD_CONTROL_ROOT"] = str(cwd)

        proc = subprocess.run(
            [sys.executable, "-m", "atdd", *argv],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        return proc, (proc.stdout or "") + (proc.stderr or "")

    def test_real_coach_reconcile_reaches_guard_no_unbound_no_live_call(self, tmp_path):
        """`atdd coach reconcile` in an isolated tmp cwd with no manifest drives the
        REAL IssueManager.reconcile() to its manifest-not-found guard (proving the
        verb delegated to the real engine) with no UnboundLocalError — and, because
        reconcile bails at the manifest check BEFORE any gh/git call, it can never
        backfill or mutate a live worktree."""
        _proc, combined = self._run(["coach", "reconcile"], tmp_path)

        assert "UnboundLocalError" not in combined, combined
        assert ".atdd/manifest.yaml not found" in combined, (
            "coach reconcile did not reach the real reconcile() manifest guard — "
            f"the delegation may not have executed.\n--- output ---\n{combined}"
        )

    def test_deprecated_issue_reconcile_reaches_same_guard_and_warns(self, tmp_path):
        """The deprecated `atdd issue reconcile` reaches the SAME engine (same
        manifest guard) and prints the stderr deprecation notice."""
        proc, combined = self._run(["issue", "reconcile"], tmp_path)

        assert "UnboundLocalError" not in combined, combined
        assert ".atdd/manifest.yaml not found" in combined, combined
        assert "atdd coach reconcile" in (proc.stderr or ""), (
            "deprecated path must signpost the canonical verb on stderr.\n"
            f"--- stderr ---\n{proc.stderr}"
        )
