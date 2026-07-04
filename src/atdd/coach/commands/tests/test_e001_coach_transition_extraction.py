# URN: test:coach-verb-split:coach-verb-split:E001-INTEGRATION-001-coach-transition-extraction
# Acceptance: acc:coach-verb-split:E001-UNIT-001-verb-auto-discovery
# Acceptance: acc:coach-verb-split:E001-INTEGRATION-001-coach-transition-applies-identically
# WMBT: wmbt:coach-verb-split:E001
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""C1 (#1304) — `atdd coach transition` extraction parity + the auto-discovery
CLI-registration pattern (LEAD, umbrella #1303).

HERMETIC BY CONSTRUCTION: every test that reaches the transition path runs with
a temp cwd + temp ATDD_CONTROL_ROOT and a THROWAWAY issue number (never a live
issue), and stubs every real-IO seam (github/store/manifest via
`IssueManager.update`/`archive`, plus the gate/compliance/re-enter helpers). No
test may transition, archive, or close a real issue.

Behavior parity proved (mirrors the old `atdd issue --status` path):
  1. `atdd coach transition <N> <TO>` routes through the auto-discovery dispatch
     to `issue_transition.apply_transition`, which reaches `IssueManager.update()`
     with the same (issue_id, status, force) args — the store-first /
     manifest-mirror / github-label writes live inside update() (covered by its
     own suite); here we prove the verb DELEGATES to it.
  2. The operator-approval token is still enforced: with the approval check
     registered + the transition gated, a missing token makes the verb return
     non-zero AND `IssueManager.update()` (the label/phase swap) is never
     reached — an anti-theater "did-not-occur" assertion via a recording spy.
  3. The deprecated `atdd issue <N> --status <TO>` still works: it warns on
     stderr and delegates to the new verb entry point.
  4. The pattern is copyable: the coach_verbs package auto-discovers each verb
     drop-in with zero shared edits.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.platform]

# A number that is NOT any real GitHub issue — see the hermeticity note above.
_FAKE_ISSUE = 999001


@pytest.fixture
def hermetic(tmp_path, monkeypatch):
    """Isolate cwd + control root so any leaked store/manifest write is contained."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def planned_issue():
    return {
        "number": _FAKE_ISSUE,
        "title": "throwaway",
        "state": "OPEN",
        "labels": [{"name": "atdd-issue"}, {"name": "atdd:PLANNED"}],
        "body": "",
    }


@pytest.fixture
def clean_registry():
    from atdd.coach.gate.registry import GATE_REGISTRY

    before = GATE_REGISTRY.checks_for("PLANNED", "RED")
    yield GATE_REGISTRY
    GATE_REGISTRY.clear("PLANNED", "RED")
    for chk in before:
        GATE_REGISTRY.register("PLANNED", "RED", chk)


# ---------------------------------------------------------------------------
# 1. The pattern: auto-discovery resolves the verb with zero shared edits
# ---------------------------------------------------------------------------
class TestCoachVerbAutoDiscovery:
    def test_resolve_verb_finds_transition_dropin(self):
        from atdd.coach.commands.coach_verbs import discover, resolve_verb
        from atdd.coach.commands.issue_transition import run as canonical_run

        assert resolve_verb("transition") is canonical_run
        assert discover().get("transition") is canonical_run

    def test_resolve_verb_returns_none_for_unknown_and_numeric(self):
        from atdd.coach.commands.coach_verbs import resolve_verb

        assert resolve_verb("nope") is None
        # A leading issue number must NOT resolve as a verb (it falls through to
        # the coach state-machine path).
        assert resolve_verb("1304") is None


# ---------------------------------------------------------------------------
# 2. Parity: the verb applies the transition identically (delegates to update)
# ---------------------------------------------------------------------------
class TestCoachTransitionAppliesIdentically:
    def test_run_cli_routes_transition_to_update(self, hermetic):
        """run_cli(['transition', N, 'GREEN']) reaches IssueManager.update() with
        the same args the old `atdd issue --status GREEN` did, rc 0. A non-
        terminal target so archive() is never involved."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        from atdd.coach.commands.issue import IssueManager

        update_spy = MagicMock(return_value=0)
        with patch.object(IssueLifecycle, "_transition_gate", return_value=0), \
             patch.object(IssueLifecycle, "_compliance_gate", return_value=0), \
             patch.object(IssueLifecycle, "_reenter_display_only", return_value=0), \
             patch.object(IssueManager, "update", update_spy):
            rc = coach.run_cli(["transition", str(_FAKE_ISSUE), "GREEN"])

        assert rc == 0
        update_spy.assert_called_once()
        _, kwargs = update_spy.call_args
        assert kwargs == {"issue_id": str(_FAKE_ISSUE), "status": "GREEN", "force": False}

    def test_run_cli_transition_forwards_force(self, hermetic):
        """--force reaches update() as force=True. Uses GREEN (non-terminal) so
        archive() is never called even if update were real."""
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        from atdd.coach.commands.issue import IssueManager

        update_spy = MagicMock(return_value=0)
        with patch.object(IssueLifecycle, "_transition_gate", return_value=0), \
             patch.object(IssueLifecycle, "_compliance_gate", return_value=0), \
             patch.object(IssueLifecycle, "_reenter_display_only", return_value=0), \
             patch.object(IssueManager, "update", update_spy):
            rc = coach.run_cli(["transition", str(_FAKE_ISSUE), "GREEN", "--force"])

        assert rc == 0
        _, kwargs = update_spy.call_args
        assert kwargs["force"] is True


# ---------------------------------------------------------------------------
# 3. Token enforcement: no operator token => transition refused, update unreached
# ---------------------------------------------------------------------------
class TestCoachTransitionEnforcesOperatorToken:
    def test_missing_token_refuses_and_never_swaps_label(
        self, hermetic, planned_issue, clean_registry
    ):
        from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
        from atdd.coach.commands import coach
        from atdd.coach.commands.issue_lifecycle import IssueLifecycle
        from atdd.coach.commands.issue import IssueManager

        clean_registry.register("PLANNED", "RED", ApprovalTokenGateCheck(signing_key="k"))
        config = {"gate": {"transitions": {"PLANNED->RED": True}}}

        update_spy = MagicMock(return_value=0)
        with patch.object(IssueLifecycle, "_fetch_issue", return_value=planned_issue), \
             patch.object(IssueLifecycle, "_load_config", return_value=config), \
             patch.object(IssueManager, "update", update_spy):
            rc = coach.run_cli(["transition", str(_FAKE_ISSUE), "RED"])

        assert rc != 0, "a missing approval token must make the verb return non-zero"
        assert not update_spy.called, (
            "the transition occurred despite no operator token — "
            "IssueManager.update() (the label/phase swap) must never be reached"
        )


# ---------------------------------------------------------------------------
# 4. Deprecated shim: `atdd issue --status` warns on stderr + delegates
# ---------------------------------------------------------------------------
class TestDeprecatedIssueStatusShim:
    def test_issue_status_warns_and_delegates(self, hermetic, capsys, monkeypatch):
        import atdd.cli as cli
        import atdd.coach.commands.issue_transition as it

        monkeypatch.setattr(
            "sys.argv", ["atdd", "issue", str(_FAKE_ISSUE), "--status", "PLANNED"]
        )
        # Patch the delegate so NO real transition can occur even if wiring drifts.
        delegate_spy = MagicMock(return_value=0)
        with patch.object(it, "run", delegate_spy):
            rc = cli.main()

        assert rc == 0
        delegate_spy.assert_called_once_with([str(_FAKE_ISSUE), "PLANNED"])
        err = capsys.readouterr().err
        assert "deprecated" in err.lower()
        assert "atdd coach transition" in err

    def test_issue_status_force_is_forwarded(self, hermetic, monkeypatch):
        import atdd.cli as cli
        import atdd.coach.commands.issue_transition as it

        monkeypatch.setattr(
            "sys.argv",
            ["atdd", "issue", str(_FAKE_ISSUE), "--status", "RED", "--force"],
        )
        delegate_spy = MagicMock(return_value=0)
        with patch.object(it, "run", delegate_spy):
            rc = cli.main()

        assert rc == 0
        delegate_spy.assert_called_once_with([str(_FAKE_ISSUE), "RED", "--force"])
