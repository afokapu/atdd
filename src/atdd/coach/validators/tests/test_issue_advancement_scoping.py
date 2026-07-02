"""Scoping tests for issue-advancement (issue #1296).

SPEC-COACH-PRGATE-0003 previously scanned the last ~20 merged PRs' *live*
issue phases and blocked CI if ANY linked issue was momentarily at
INIT/PLANNED. That coupled every PR — and the release commit — to unrelated
issue hygiene, non-deterministically (the #1172/#1274/#1285 whack-a-mole).

The fix scopes the BLOCKING path to the PR-under-validation's own linked
issue, and downgrades the cross-PR sweep to a non-blocking advisory. These
tests pin that contract deterministically with a mocked PRManager — no
network, no live GitHub state.
"""
import atdd.coach.validators.test_issue_advancement as mod
from atdd.coach.validators.test_issue_advancement import (
    _current_pr_number,
    _evaluate_pr,
    scan_issue_advancement,
)


def _issue(phase=None, state="OPEN", labels=None):
    lbls = list(labels or [])
    if phase is not None:
        lbls.append({"name": f"atdd:{phase}"})
    return {"state": state, "labels": lbls}


class FakePRManager:
    """Stand-in for PRManager driven by in-memory fixtures.

    ``resolutions`` maps pr_number -> the dict resolve_linked_issue returns
    (or None). ``merged`` is the recently-merged PR summary list. Branch
    resolution is controlled by ``branch``/``existing_pr``/``merged_pr``.
    """

    def __init__(self, target_dir=None, *, resolutions=None, merged=None,
                 branch=None, existing_pr=None, merged_pr=None):
        self._resolutions = resolutions or {}
        self._merged = merged or []
        self._branch = branch
        self._existing_pr = existing_pr
        self._merged_pr = merged_pr

    def resolve_linked_issue(self, pr_number):
        return self._resolutions.get(pr_number)

    def fetch_recently_merged_prs(self, limit=20):
        return self._merged

    def _detect_branch(self):
        return self._branch

    def _existing_pr_for_branch(self, branch):
        return self._existing_pr

    def _merged_pr_for_branch(self, branch):
        return self._merged_pr


def _install(monkeypatch, mgr):
    monkeypatch.setattr(mod, "PRManager", lambda target_dir=None: mgr)


def _clear_pr_env(monkeypatch):
    for var in ("GITHUB_REF", "GITHUB_HEAD_REF", "GITHUB_PR_NUMBER", "PR_NUMBER"):
        monkeypatch.delenv(var, raising=False)


# ---------------------------------------------------------------------------
# _current_pr_number
# ---------------------------------------------------------------------------


class TestCurrentPrNumber:
    def test_parses_github_ref_pull_merge(self, monkeypatch):
        _clear_pr_env(monkeypatch)
        monkeypatch.setenv("GITHUB_REF", "refs/pull/1296/merge")
        assert _current_pr_number(FakePRManager()) == 1296

    def test_parses_github_ref_pull_head(self, monkeypatch):
        _clear_pr_env(monkeypatch)
        monkeypatch.setenv("GITHUB_REF", "refs/pull/77/head")
        assert _current_pr_number(FakePRManager()) == 77

    def test_env_pr_number_fallback(self, monkeypatch):
        _clear_pr_env(monkeypatch)
        monkeypatch.setenv("GITHUB_PR_NUMBER", "512")
        assert _current_pr_number(FakePRManager()) == 512

    def test_branch_open_pr_fallback(self, monkeypatch):
        _clear_pr_env(monkeypatch)
        mgr = FakePRManager(
            branch="feat/x",
            existing_pr="https://github.com/o/r/pull/1296",
        )
        assert _current_pr_number(mgr) == 1296

    def test_branch_merged_pr_fallback(self, monkeypatch):
        _clear_pr_env(monkeypatch)
        mgr = FakePRManager(
            branch="feat/x",
            existing_pr=None,
            merged_pr="https://github.com/o/r/pull/808",
        )
        assert _current_pr_number(mgr) == 808

    def test_returns_none_when_nothing_resolvable(self, monkeypatch):
        _clear_pr_env(monkeypatch)
        assert _current_pr_number(FakePRManager(branch=None)) is None


# ---------------------------------------------------------------------------
# _evaluate_pr — per-PR staleness decision (shared by both paths)
# ---------------------------------------------------------------------------


class TestEvaluatePr:
    def _mgr(self, phase, **issue_kwargs):
        res = {
            "issue_number": 42,
            "phase_label": phase,
            "issue_data": _issue(phase=phase, **issue_kwargs),
        }
        return FakePRManager(resolutions={5: res})

    def test_flags_init(self):
        msg = _evaluate_pr(self._mgr("INIT"), {"number": 5, "mergedAt": "t"})
        assert msg is not None and "#42" in msg and "INIT" in msg

    def test_flags_planned(self):
        assert _evaluate_pr(self._mgr("PLANNED"), {"number": 5}) is not None

    def test_ok_for_red(self):
        assert _evaluate_pr(self._mgr("RED"), {"number": 5}) is None

    def test_skips_closed_issue(self):
        assert _evaluate_pr(self._mgr("INIT", state="CLOSED"), {"number": 5}) is None

    def test_skips_terminal_phase(self):
        assert _evaluate_pr(self._mgr("COMPLETE"), {"number": 5}) is None

    def test_skips_non_lifecycle(self):
        mgr = self._mgr("INIT", labels=[{"name": "tracking"}])
        assert _evaluate_pr(mgr, {"number": 5}) is None

    def test_none_when_unlinked(self):
        assert _evaluate_pr(FakePRManager(resolutions={}), {"number": 5}) is None


# ---------------------------------------------------------------------------
# scan_issue_advancement — the scoping contract
# ---------------------------------------------------------------------------


class TestScanScoping:
    def test_own_issue_fine_other_pr_init_passes(self, monkeypatch):
        """KEY: own PR's issue is fine (RED); another merged PR is momentarily
        INIT. The gate MUST pass — no coupling to unrelated hygiene."""
        _clear_pr_env(monkeypatch)
        monkeypatch.setenv("GITHUB_REF", "refs/pull/1296/merge")
        resolutions = {
            1296: {"issue_number": 1296, "phase_label": "RED",
                   "issue_data": _issue(phase="RED")},
            999: {"issue_number": 999, "phase_label": "INIT",
                  "issue_data": _issue(phase="INIT")},
        }
        mgr = FakePRManager(
            resolutions=resolutions,
            merged=[{"number": 999, "mergedAt": "t"}, {"number": 1296}],
        )
        _install(monkeypatch, mgr)
        count, violations = scan_issue_advancement(None)
        assert count == 0
        assert violations == []

    def test_own_issue_init_still_blocks(self, monkeypatch):
        """Own-PR enforcement preserved: own issue at INIT → blocking."""
        _clear_pr_env(monkeypatch)
        monkeypatch.setenv("GITHUB_REF", "refs/pull/1296/merge")
        resolutions = {
            1296: {"issue_number": 1296, "phase_label": "INIT",
                   "issue_data": _issue(phase="INIT")},
        }
        mgr = FakePRManager(resolutions=resolutions, merged=[])
        _install(monkeypatch, mgr)
        count, violations = scan_issue_advancement(None)
        assert count == 1
        assert "#1296" in violations[0]

    def test_no_own_pr_is_deterministic_pass(self, monkeypatch):
        """No resolvable own PR (e.g. local validate) + an unrelated INIT PR
        → deterministic green (blocking set empty)."""
        _clear_pr_env(monkeypatch)
        resolutions = {
            999: {"issue_number": 999, "phase_label": "INIT",
                  "issue_data": _issue(phase="INIT")},
        }
        mgr = FakePRManager(
            resolutions=resolutions,
            merged=[{"number": 999, "mergedAt": "t"}],
            branch=None,
        )
        _install(monkeypatch, mgr)
        count, violations = scan_issue_advancement(None)
        assert count == 0
        assert violations == []
