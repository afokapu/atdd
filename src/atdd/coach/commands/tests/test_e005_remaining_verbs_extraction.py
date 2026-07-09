# URN: test:coach-verb-split:coach-verb-split:E005-INTEGRATION-001-remaining-verbs-extraction
# Acceptance: acc:coach-verb-split:E005-UNIT-001-remaining-verbs-auto-discovery-and-prefix-decouple
# Acceptance: acc:coach-verb-split:E005-INTEGRATION-001-coach-verbs-delegate-identically-and-shims-warn
# Acceptance: acc:coach-verb-split:E005-SMOKE-001-real-remaining-verbs-and-hook-gate-in-temp-control-root
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""C5a (#1382) — extraction parity for the SIX remaining monolith-only `atdd
issue` verbs, plus the TYPE_TO_PREFIX / ALLOWED_BRANCH_PREFIXES decouple and the
pre-commit hook repoint (umbrella #1303; the monolith deletion itself is C5b /
#1309, NOT this issue).

DELEGATION-ONLY: none of the six verbs is reimplemented — each new `atdd coach
<verb>` and each deprecated `atdd issue` shim delegates to the SAME existing
function/method:

    atdd coach issue-review <N>   -> issue_review.run(issue_number=N, ...)   (#508 LLM review)
    atdd coach is-registered <B>  -> IssueManager.branch_is_registered(B)
    atdd coach check <N>          -> IssueLifecycle.check(N)
    atdd coach close-wmbt <N> <I> -> IssueLifecycle.close_wmbt(N, I, force=...)
    atdd coach sync-wmbts <N>     -> IssueManager.sync_wmbts(N)
    atdd coach enter <N>          -> IssueLifecycle.enter(N)

These tests prove the WIRING (auto-discovery + delegation + deprecated-shim
warn/delegate), never the engines (each has its own suite).

HERMETIC BY CONSTRUCTION (feedback_transition_tests_must_be_hermetic): every test
runs in a temp cwd + temp ATDD_CONTROL_ROOT, and every delegate is stubbed with a
recording spy, so no real issue/branch/manifest/store is ever read or mutated and
no live `gh`/`git` call is made. The #1304 incident archived a real issue by
testing on it — never route a real number/branch through an unstubbed engine.

`atdd coach review` is deliberately NOT reused: it already belongs to the coach
disposition/merge-readiness command (coach_review.run_review), resolved BEFORE the
coach_verbs auto-discovery path. The #508 LLM issue-review therefore lands as the
non-colliding `atdd coach issue-review <N>`.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]

# A sentinel exit code distinct from 0/1/2 so a delegated call is unambiguous.
_SENTINEL_RC = 7
# A clearly-fake issue number / branch — everything is spied, so no I/O occurs,
# but keep it far from any real issue as defence-in-depth.
_FAKE_ISSUE = 424242
_FAKE_BRANCH = "refactor/never-a-real-branch-e005"


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Isolate cwd + control root so any leaked store/manifest write is contained."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


# ===========================================================================
# 1. UNIT — auto-discovery resolves all six drop-ins with zero shared edits,
#    and the prefix constants are decoupled into issue_prefixes.
#    (acc:coach-verb-split:E005-UNIT-001)
# ===========================================================================
_VERBS = [
    ("issue-review", "issue_review"),
    ("is-registered", "is_registered"),
    ("check", "check"),
    ("close-wmbt", "close_wmbt"),
    ("sync-wmbts", "sync_wmbts"),
    ("enter", "enter"),
]


class TestRemainingVerbsAutoDiscovery:
    @pytest.mark.parametrize("token,modname", _VERBS)
    def test_resolve_verb_finds_each_dropin(self, token, modname):
        import importlib

        from atdd.coach.commands.coach_verbs import discover, resolve_verb

        module = importlib.import_module(f"atdd.coach.commands.coach_verbs.{modname}")
        assert module.VERB == token
        assert callable(module.run)
        assert resolve_verb(token) is module.run
        assert discover().get(token) is module.run

    def test_resolve_verb_returns_none_for_unknown_and_numeric(self):
        from atdd.coach.commands.coach_verbs import resolve_verb

        assert resolve_verb("nope") is None
        assert resolve_verb("1382") is None

    def test_issue_review_verb_does_not_shadow_coach_review(self):
        """The extracted LLM issue-review must NOT collide with the pre-existing
        `atdd coach review` (coach_review.run_review). It lives under its own
        `issue-review` token."""
        from atdd.coach.commands.coach_verbs import resolve_verb

        # No `review` drop-in is registered by C5a (that token stays with
        # coach_review.run_review, dispatched earlier in run_cli).
        assert resolve_verb("review") is None


class TestPrefixDecouple:
    def test_prefixes_live_in_neutral_module_and_issue_reexports(self):
        """TYPE_TO_PREFIX / ALLOWED_BRANCH_PREFIXES move to the neutral
        issue_prefixes module; issue.py re-exports the SAME objects so nothing
        breaks now, and C5b can delete the monolith without losing them."""
        from atdd.coach.commands import issue, issue_prefixes

        assert issue_prefixes.TYPE_TO_PREFIX == {
            "implementation": "feat",
            "migration": "feat",
            "refactor": "refactor",
            "analysis": "chore",
            "planning": "chore",
            "cleanup": "chore",
            "tracking": "chore",
        }
        assert issue_prefixes.ALLOWED_BRANCH_PREFIXES == (
            "feat", "fix", "refactor", "chore", "docs", "devops",
        )
        # issue.py re-exports the identical objects (single source of truth).
        assert issue.TYPE_TO_PREFIX is issue_prefixes.TYPE_TO_PREFIX
        assert issue.ALLOWED_BRANCH_PREFIXES is issue_prefixes.ALLOWED_BRANCH_PREFIXES

    def test_branch_and_pr_import_prefixes_from_neutral_module(self):
        """branch.py / pr.py must no longer hard-depend on issue.py for the
        prefixes — they bind the SAME object issue_prefixes defines."""
        from atdd.coach.commands import branch, issue_prefixes, pr

        assert branch.TYPE_TO_PREFIX is issue_prefixes.TYPE_TO_PREFIX
        assert branch.ALLOWED_BRANCH_PREFIXES is issue_prefixes.ALLOWED_BRANCH_PREFIXES
        assert pr.TYPE_TO_PREFIX is issue_prefixes.TYPE_TO_PREFIX


# ===========================================================================
# 2. INTEGRATION — each verb delegates identically; each shim warns + delegates.
#    (acc:coach-verb-split:E005-INTEGRATION-001)
# ===========================================================================
class TestIssueReviewDelegation:
    def test_coach_issue_review_delegates_and_forwards_flags(self, hermetic):
        from atdd.coach.commands import coach
        import atdd.coach.commands.issue_review as ir

        spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(ir, "run", spy):
            rc = coach.run_cli([
                "issue-review", str(_FAKE_ISSUE),
                "--passes", "3",
                "--llms", "a,b,c",
                "--dimensions", "correctness,clarity",
                "--show", "--force",
            ])

        assert rc == _SENTINEL_RC
        spy.assert_called_once()
        _, kw = spy.call_args
        assert kw["issue_number"] == _FAKE_ISSUE
        assert kw["passes"] == 3
        assert kw["llms"] == ["a", "b", "c"]
        assert kw["dimensions"] == ["correctness", "clarity"]
        assert kw["show"] is True
        assert kw["force"] is True

    def test_coach_issue_review_requires_a_number(self, hermetic):
        from atdd.coach.commands import coach
        import atdd.coach.commands.issue_review as ir

        spy = MagicMock(return_value=0)
        with patch.object(ir, "run", spy):
            rc = coach.run_cli(["issue-review"])
        assert rc == 1
        spy.assert_not_called()

    def test_deprecated_issue_review_warns_and_delegates(self, hermetic, capsys, monkeypatch):
        import atdd.cli as cli
        import atdd.coach.commands.issue_review as ir

        monkeypatch.setattr("sys.argv", ["atdd", "issue", "review", str(_FAKE_ISSUE)])
        spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(ir, "run", spy):
            rc = cli.main()

        assert rc == _SENTINEL_RC
        spy.assert_called_once()
        assert spy.call_args.kwargs["issue_number"] == _FAKE_ISSUE
        err = capsys.readouterr().err
        assert "deprecated" in err.lower()
        assert "atdd coach issue-review" in err


class TestIsRegisteredDelegation:
    def test_coach_is_registered_returns_zero_when_registered(self, hermetic):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        spy = MagicMock(return_value=True)
        with patch.object(IssueManager, "branch_is_registered", spy):
            rc = coach.run_cli(["is-registered", _FAKE_BRANCH])
        assert rc == 0
        spy.assert_called_once_with(_FAKE_BRANCH)

    def test_coach_is_registered_returns_one_when_unregistered(self, hermetic):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        spy = MagicMock(return_value=False)
        with patch.object(IssueManager, "branch_is_registered", spy):
            rc = coach.run_cli(["is-registered", _FAKE_BRANCH])
        assert rc == 1

    def test_coach_is_registered_usage_error_when_no_branch(self, hermetic):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        spy = MagicMock(return_value=True)
        with patch.object(IssueManager, "branch_is_registered", spy):
            rc = coach.run_cli(["is-registered"])
        assert rc == 2
        spy.assert_not_called()

    def test_deprecated_issue_is_registered_warns_and_delegates(self, hermetic, capsys, monkeypatch):
        import atdd.cli as cli
        from atdd.coach.commands.issue import IssueManager

        monkeypatch.setattr("sys.argv", ["atdd", "issue", "is-registered", _FAKE_BRANCH])
        spy = MagicMock(return_value=True)
        with patch.object(IssueManager, "branch_is_registered", spy):
            rc = cli.main()
        assert rc == 0
        spy.assert_called_once_with(_FAKE_BRANCH)
        err = capsys.readouterr().err
        assert "deprecated" in err.lower()
        assert "atdd coach is-registered" in err


class TestCheckDelegation:
    def test_coach_check_delegates_to_lifecycle_check(self, hermetic):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle

        spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(IssueLifecycle, "check", spy):
            rc = coach.run_cli(["check", str(_FAKE_ISSUE)])
        assert rc == _SENTINEL_RC
        spy.assert_called_once_with(_FAKE_ISSUE)

    def test_deprecated_issue_check_warns_and_delegates(self, hermetic, capsys, monkeypatch):
        import atdd.cli as cli
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle

        monkeypatch.setattr("sys.argv", ["atdd", "issue", str(_FAKE_ISSUE), "--check"])
        spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(IssueLifecycle, "check", spy):
            rc = cli.main()
        assert rc == _SENTINEL_RC
        spy.assert_called_once_with(_FAKE_ISSUE)
        err = capsys.readouterr().err
        assert "deprecated" in err.lower()
        assert "atdd coach check" in err


class TestCloseWmbtDelegation:
    def test_coach_close_wmbt_delegates_with_force(self, hermetic):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle

        spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(IssueLifecycle, "close_wmbt", spy):
            rc = coach.run_cli(["close-wmbt", str(_FAKE_ISSUE), "E005", "--force"])
        assert rc == _SENTINEL_RC
        spy.assert_called_once_with(_FAKE_ISSUE, "E005", force=True)

    def test_coach_close_wmbt_defaults_force_false(self, hermetic):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle

        spy = MagicMock(return_value=0)
        with patch.object(IssueLifecycle, "close_wmbt", spy):
            coach.run_cli(["close-wmbt", str(_FAKE_ISSUE), "E005"])
        spy.assert_called_once_with(_FAKE_ISSUE, "E005", force=False)

    def test_deprecated_issue_close_wmbt_warns_and_delegates(self, hermetic, capsys, monkeypatch):
        import atdd.cli as cli
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle

        monkeypatch.setattr(
            "sys.argv",
            ["atdd", "issue", str(_FAKE_ISSUE), "--close-wmbt", "E005"],
        )
        spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(IssueLifecycle, "close_wmbt", spy):
            rc = cli.main()
        assert rc == _SENTINEL_RC
        spy.assert_called_once_with(_FAKE_ISSUE, "E005", force=False)
        err = capsys.readouterr().err
        assert "deprecated" in err.lower()
        assert "atdd coach close-wmbt" in err


class TestSyncWmbtsDelegation:
    def test_coach_sync_wmbts_maps_nonneg_to_zero(self, hermetic):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        spy = MagicMock(return_value=3)  # rc >= 0 -> exit 0
        with patch.object(IssueManager, "sync_wmbts", spy):
            rc = coach.run_cli(["sync-wmbts", str(_FAKE_ISSUE)])
        assert rc == 0
        spy.assert_called_once_with(_FAKE_ISSUE)

    def test_coach_sync_wmbts_maps_negative_to_one(self, hermetic):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue import IssueManager

        spy = MagicMock(return_value=-1)  # rc < 0 -> exit 1
        with patch.object(IssueManager, "sync_wmbts", spy):
            rc = coach.run_cli(["sync-wmbts", str(_FAKE_ISSUE)])
        assert rc == 1

    def test_deprecated_issue_sync_wmbts_warns_and_delegates(self, hermetic, capsys, monkeypatch):
        import atdd.cli as cli
        from atdd.coach.commands.issue import IssueManager

        monkeypatch.setattr("sys.argv", ["atdd", "issue", str(_FAKE_ISSUE), "--sync-wmbts"])
        spy = MagicMock(return_value=0)
        with patch.object(IssueManager, "sync_wmbts", spy):
            rc = cli.main()
        assert rc == 0
        spy.assert_called_once_with(_FAKE_ISSUE)
        err = capsys.readouterr().err
        assert "deprecated" in err.lower()
        assert "atdd coach sync-wmbts" in err


class TestEnterDelegation:
    def test_coach_enter_delegates_to_lifecycle_enter(self, hermetic):
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle

        spy = MagicMock(return_value=_SENTINEL_RC)
        with patch.object(IssueLifecycle, "enter", spy):
            rc = coach.run_cli(["enter", str(_FAKE_ISSUE)])
        assert rc == _SENTINEL_RC
        spy.assert_called_once_with(_FAKE_ISSUE)

    def test_bare_issue_number_still_reaches_enter(self, hermetic):
        """The bare `atdd issue <N>` shim (#1307, unchanged) still reaches the
        SAME IssueLifecycle.enter engine that `atdd coach enter` delegates to —
        behavior parity is preserved without re-pointing #1307's shim."""
        import atdd.cli as cli
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle

        with patch("sys.argv", ["atdd", "issue", str(_FAKE_ISSUE)]):
            spy = MagicMock(return_value=0)
            with patch.object(IssueLifecycle, "enter", spy):
                cli.main()
        spy.assert_called_once()
        args, _ = spy.call_args
        assert args[0] == _FAKE_ISSUE


# ===========================================================================
# 3. SMOKE — real subprocess: `atdd coach is-registered` reaches the real gate,
#    the deprecated form reaches the same gate + warns, and the pre-commit hook
#    now invokes `atdd coach is-registered`.
#    (acc:coach-verb-split:E005-SMOKE-001)
# ===========================================================================
@pytest.mark.smoke
class TestRemainingVerbsSmokeInTempControlRoot:
    def _run(self, argv, cwd):
        import os
        import subprocess
        import sys
        from pathlib import Path

        import atdd

        # Run the SAME atdd the test process imports (code under test), pinned via
        # an ABSOLUTE source root on PYTHONPATH; isolate with a temp control root.
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

    def test_real_coach_is_registered_reaches_gate_no_crash(self, tmp_path):
        """In an isolated empty temp cwd (nothing to check) the REAL
        IssueManager.branch_is_registered gate returns True -> exit 0, with no
        UnboundLocalError/traceback and no live gh/git mutation, proving the verb
        delegated to the real gate."""
        proc, combined = self._run(["coach", "is-registered", _FAKE_BRANCH], tmp_path)
        assert "UnboundLocalError" not in combined, combined
        assert "Traceback" not in combined, combined
        assert proc.returncode == 0, combined

    def test_deprecated_issue_is_registered_reaches_same_gate_and_warns(self, tmp_path):
        proc, combined = self._run(["issue", "is-registered", _FAKE_BRANCH], tmp_path)
        assert "UnboundLocalError" not in combined, combined
        assert proc.returncode == 0, combined
        assert "atdd coach is-registered" in (proc.stderr or ""), (
            "deprecated path must signpost the canonical verb on stderr.\n"
            f"--- stderr ---\n{proc.stderr}"
        )

    def test_pre_commit_hook_invokes_coach_is_registered(self):
        """The pre-commit hook's branch-registration gate must call `atdd coach
        is-registered` (not `atdd issue is-registered`) so C5b's deletion of the
        `atdd issue` monolith cannot break commits."""
        from pathlib import Path

        import atdd

        repo_root = Path(atdd.__file__).resolve().parent.parent.parent
        hook = repo_root / ".atdd" / "hooks" / "pre-commit"
        text = hook.read_text()
        assert "atdd coach is-registered" in text, (
            "pre-commit hook was not repointed to `atdd coach is-registered`"
        )
        # The legacy invocation must be gone from the executable gate line.
        assert "atdd issue is-registered \"$BRANCH\"" not in text, (
            "legacy `atdd issue is-registered \"$BRANCH\"` gate line still present"
        )
