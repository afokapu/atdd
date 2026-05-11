# URN: test:integration-hardening:two-phase-commit-wiring:P001-INTEGRATION-002-cleanup
# Acceptance: acc:integration-hardening:P001-INTEGRATION-002-cleanup
# WMBT: wmbt:integration-hardening:P001
# Phase: RED
# Layer: integration
"""P001-INTEGRATION-002 — post-MERGED, worktree is removed.

Verifies that:
  1. After a successful merge, the handler attempts to remove the
     worktree for the issue (git worktree remove --force).
  2. If git worktree list returns a matching worktree for the issue
     number, git worktree remove is called for that path.
  3. Cleanup failure does NOT change HandlerResult.HANDLED — the issue
     is already merged; don't block MERGED state on cleanup errors
     (per review note 2026-05-11 afokapu).

Note: cmux tab closure is best-effort and handled via the multiplexer
backend when a session is found in list_workspaces(). Tests here focus
on the worktree cleanup path which is always attempted.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytestmark = [pytest.mark.platform]


def _make_ctx(issue_number: int = 590, *, auto_merge: bool = True):
    from atdd.coach.handlers.state_machine import CoachContext
    return CoachContext(issue_number=issue_number, auto_merge=auto_merge)


def _make_transition():
    from atdd.coach.handlers.state_machine import Phase, Transition
    return Transition(src=Phase.COMPLETE, dst=Phase.MERGED)


_WORKTREE_LIST_WITH_590 = """\
worktree /Users/dev/atdd/feat-coach-v9-p2-wiring-590
HEAD abc123
branch refs/heads/feat/coach-v9-p2-two-phase-commit-wiring-590

worktree /Users/dev/atdd/main
HEAD def456
branch refs/heads/main

"""

_WORKTREE_LIST_WITHOUT_590 = """\
worktree /Users/dev/atdd/main
HEAD def456
branch refs/heads/main

"""


class _CallRouter:
    """Routes subprocess.run calls to different outcomes per command."""

    def __init__(self, worktree_list_output: str = "", remove_returncode: int = 0):
        self.calls: list[list[str]] = []
        self._list_output = worktree_list_output
        self._remove_rc = remove_returncode

    def run(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        key = " ".join(cmd)
        if "worktree" in key and "list" in key:
            return SimpleNamespace(returncode=0, stdout=self._list_output, stderr="")
        if "worktree" in key and "remove" in key:
            return SimpleNamespace(returncode=self._remove_rc, stdout="", stderr="cleanup failed" if self._remove_rc else "")
        # Default: success for atdd pr and gh pr merge
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def cmd_strs(self) -> list[str]:
        return [" ".join(c) for c in self.calls]


def test_worktree_remove_called_when_matching_worktree_found(monkeypatch):
    """P001-INTEGRATION-002: handler calls git worktree remove --force <path> after merge."""
    import atdd.coach.handlers.two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import HandlerResult

    router = _CallRouter(worktree_list_output=_WORKTREE_LIST_WITH_590)
    monkeypatch.setattr(tpc, "subprocess", router)

    result = tpc.handle(_make_ctx(590), _make_transition())

    assert result == HandlerResult.HANDLED
    remove_calls = [c for c in router.cmd_strs() if "worktree" in c and "remove" in c]
    assert remove_calls, "Expected git worktree remove call"
    assert "--force" in remove_calls[0], "--force must be passed to worktree remove"
    assert "feat-coach-v9-p2-wiring-590" in remove_calls[0] or "590" in remove_calls[0], (
        f"Worktree path for #590 not in remove call: {remove_calls[0]}"
    )


def test_worktree_remove_skipped_when_no_matching_worktree(monkeypatch):
    """P001-INTEGRATION-002: no worktree remove call when no matching worktree found."""
    import atdd.coach.handlers.two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import HandlerResult

    router = _CallRouter(worktree_list_output=_WORKTREE_LIST_WITHOUT_590)
    monkeypatch.setattr(tpc, "subprocess", router)

    result = tpc.handle(_make_ctx(590), _make_transition())

    assert result == HandlerResult.HANDLED
    remove_calls = [c for c in router.cmd_strs() if "worktree" in c and "remove" in c]
    assert not remove_calls, f"Unexpected worktree remove when no match: {remove_calls}"


def test_cleanup_failure_still_returns_handled(monkeypatch):
    """P001-INTEGRATION-002: worktree removal failure → MERGED (warn log, not ERROR)."""
    import atdd.coach.handlers.two_phase_commit as tpc
    from atdd.coach.handlers.state_machine import HandlerResult

    router = _CallRouter(
        worktree_list_output=_WORKTREE_LIST_WITH_590,
        remove_returncode=1,
    )
    monkeypatch.setattr(tpc, "subprocess", router)

    result = tpc.handle(_make_ctx(590), _make_transition())

    assert result == HandlerResult.HANDLED, (
        "Cleanup failure must NOT block MERGED state; review note: cleanup fail → MERGED with warn"
    )
