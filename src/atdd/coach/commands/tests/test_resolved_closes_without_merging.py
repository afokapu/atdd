"""#1967 — reaching RESOLVED CLOSES the issue; it does not wait for a merge.

The lifecycle half of RESOLVED is inert without this one. `update()` swaps the
label and nothing else; only `archive()` closes the parent and its WMBT
sub-issues, and only COMPLETE called it. So a resolved umbrella would have sat
open forever wearing an `atdd:RESOLVED` label — terminal in the evidence model
and untouched on the board.

COMPLETE closes because the work MERGED. RESOLVED closes because the work
ANSWERED. Neither requires the other, and RESOLVED deliberately requires no PR:
an umbrella that produced only knowledge and children has nothing to merge.
"""
from __future__ import annotations

import pytest


def _run(monkeypatch, status, archived):
    """Drive the real apply_transition with its two collaborators stubbed.

    Both are imported INSIDE the function from their own modules, so they are
    patched at source rather than on issue_transition.
    """
    from atdd.coach.commands import issue as issue_mod
    from atdd.coach.commands import issue_lifecycle as lifecycle_mod
    from atdd.coach.commands.issue_transition import apply_transition

    class _FakeManager:
        def __init__(self, *a, **kw): pass
        def update(self, issue_id, status, force=False): return 0
        def archive(self, issue_id):
            archived.append(issue_id)
            return 0

    class _FakeLifecycle:
        target_dir = "."
        def __init__(self, *a, **kw): pass
        def _transition_gate(self, n, s, force=False): return 0
        def _compliance_gate(self, n, s): return 0
        def _reenter_display_only(self, n): return 0

    monkeypatch.setattr(issue_mod, "IssueManager", _FakeManager)
    monkeypatch.setattr(lifecycle_mod, "IssueLifecycle", _FakeLifecycle)
    return apply_transition(1967, status, force=False)


def test_resolved_is_a_terminal_status():
    from atdd.coach.commands.issue_lifecycle import _TERMINAL_STATUSES

    assert "RESOLVED" in _TERMINAL_STATUSES


def test_resolved_has_a_next_action_that_says_it_is_done():
    from atdd.coach.commands.issue_lifecycle import _NEXT_ACTION_HINTS

    assert "RESOLVED" in _NEXT_ACTION_HINTS
    assert any("RESOLVED" in line for line in _NEXT_ACTION_HINTS["RESOLVED"].lines)


@pytest.mark.parametrize("status", ["COMPLETE", "RESOLVED"])
def test_both_terminal_outcomes_archive(status, monkeypatch):
    """The behavioural guarantee: reaching either terminal closes the issue."""
    archived: list[str] = []

    rc = _run(monkeypatch, status, archived)

    assert rc == 0
    assert archived == ["1967"], f"{status} must close the issue"


def test_a_non_terminal_status_does_not_archive(monkeypatch):
    """Guard the other direction: PLANNED must not close anything."""
    archived: list[str] = []

    _run(monkeypatch, "PLANNED", archived)
    assert archived == []
