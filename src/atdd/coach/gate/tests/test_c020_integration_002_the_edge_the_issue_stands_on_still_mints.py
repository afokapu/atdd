# URN: test:govern-lifecycle:operator-approval-token-gate:C020-INTEGRATION-002-the-edge-the-issue-stands-on-still-mints
# Acceptance: acc:govern-lifecycle:C020-INTEGRATION-002-the-edge-the-issue-stands-on-still-mints
# WMBT: wmbt:govern-lifecycle:C020
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""C020-INTEGRATION-002 — the precondition gates the mint; it does not disable it.

The negative control for C020-INTEGRATION-001. A check that refused everything
would satisfy every assertion in that file and be catastrophically wrong, so the
discriminating cases live here: the edge the issue is standing on still mints, and
an issue that reaches a later edge legitimately can be approved for it THEN.

That second property is what makes this a precondition rather than a block. The
refusal in C020-INTEGRATION-001 is about the issue's position at that moment, not a
permanent verdict on the edge — which is exactly the difference between "you cannot
approve this yet" and "this edge is unapprovable".

And the mint's OUTPUT is unchanged: a token minted for a live edge still satisfies
the real ``ApprovalTokenGateCheck``. This issue changed which mints are allowed and
nothing whatsoever about what a minted token is or means.

RED state: this file passes before the change too, and deliberately. It is the
over-tightening half — it fails only if the precondition is wired in a way that
also refuses the mints that should succeed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.approval_check import ApprovalTokenGateCheck
from atdd.coach.gate.approval_paths import approval_token_path
from atdd.coach.gate.approve_command import run as run_approve
from atdd.coach.gate.decision import GateContext
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform]

_ISSUE = 999736
_UID = "mint-does-not-check-the-edge-is-reachable-integration-002"
_BRANCH = "feat/mint-does-not-check-the-edge-is-reachable"
_KEY = "integration-operator-key"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    monkeypatch.setenv("ATDD_APPROVAL_SIGNING_KEY", _KEY)
    return tmp_path


def _stand_at(repo: Path, phase: str) -> None:
    """Put the issue at ``phase`` — what a real transition does to the store."""
    with open_state_store(control_root=repo) as store:
        store.objects.upsert(_UID, "work_item", state=phase, data={"branch": _BRANCH})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def _mint(repo: Path, from_phase: str, to_phase: str) -> int:
    return run_approve(
        [str(_ISSUE), "--transition", f"{from_phase}->{to_phase}", "--by", "operator"],
        target_dir=repo,
        env={"USER": "operator"},
    )


def _check(repo: Path, from_phase: str, to_phase: str):
    return ApprovalTokenGateCheck(signing_key=_KEY).run(
        GateContext(
            issue_number=_ISSUE,
            from_phase=from_phase,
            to_phase=to_phase,
            worktree=repo,
        )
    )


def test_the_edge_the_issue_is_standing_on_mints(repo: Path) -> None:
    """The case the whole command exists for still works."""
    _stand_at(repo, "PLANNED")

    assert _mint(repo, "PLANNED", "RED") == 0
    assert approval_token_path(repo, _ISSUE, "PLANNED", "RED").exists()


def test_that_token_still_satisfies_the_real_gate(repo: Path) -> None:
    """The precondition changed which mints are allowed, not what a token is."""
    _stand_at(repo, "PLANNED")
    assert _mint(repo, "PLANNED", "RED") == 0

    result = _check(repo, "PLANNED", "RED")

    assert result.passed is True, result.message


def test_an_issue_that_reaches_the_edge_later_can_be_approved_then(repo: Path) -> None:
    """The refusal is about position in time, not a permanent block on the edge.

    SMOKE->REFACTOR is refused while the issue is at INIT (C020-INTEGRATION-001) and
    granted once the issue is actually at SMOKE. Same edge, same issue, opposite
    answers — which is the property that makes this a precondition.
    """
    _stand_at(repo, "INIT")
    assert _mint(repo, "SMOKE", "REFACTOR") == 1

    # The work proceeds and the issue genuinely arrives at SMOKE.
    _stand_at(repo, "SMOKE")

    assert _mint(repo, "SMOKE", "REFACTOR") == 0, (
        "an issue standing on SMOKE could not be approved for SMOKE->REFACTOR — the "
        "precondition has become a block rather than a precondition"
    )
    assert _check(repo, "SMOKE", "REFACTOR").passed is True


def test_scope_isolation_is_unaffected(repo: Path) -> None:
    """One live edge's token still does not unlock another (E050's property)."""
    _stand_at(repo, "PLANNED")
    assert _mint(repo, "PLANNED", "RED") == 0

    assert _check(repo, "RED", "GREEN").passed is False
