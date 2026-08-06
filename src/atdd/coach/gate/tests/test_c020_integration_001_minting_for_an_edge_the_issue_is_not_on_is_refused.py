# URN: test:govern-lifecycle:operator-approval-token-gate:C020-INTEGRATION-001-minting-for-an-edge-the-issue-is-not-on-is-refused
# Acceptance: acc:govern-lifecycle:C020-INTEGRATION-001-minting-for-an-edge-the-issue-is-not-on-is-refused
# WMBT: wmbt:govern-lifecycle:C020
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""C020-INTEGRATION-001 — the #1726 reproduction, closed.

What happened on 2026-08-03, minutes after #1718 shipped the honest-attribution
token. #1726 was walked through its lifecycle and EVERY transition was refused by
the template-compliance gate, correctly, because its body still carried an unfilled
placeholder::

    ❌ #1726: template non-compliant
      Unfilled placeholders (1):
        - ## Decisions: (none yet)
    Transition to PLANNED blocked by template compliance gate.

PLANNED, RED, GREEN, SMOKE, REFACTOR — refused, five times. In the same sequence,
both ``approve`` calls SUCCEEDED, leaving on disk, with the issue still at INIT::

    .atdd/runtime/issue-1726/approvals/PLANNED-RED.json
    .atdd/runtime/issue-1726/approvals/SMOKE-REFACTOR.json

Correctly attributed to ``agent:claude``, cryptographically sound, written to the
shared Control Root — and authorising two transitions that had just been refused
five times. Not inert: each satisfies ``ApprovalTokenGateCheck`` for its exact
tuple the moment the issue ever reaches that edge. An approval granted before the
work existed, waiting to be consumed.

This file drives the real mint over exactly those two edges, for an issue at INIT.

REFUSE, DO NOT WARN, and that is asserted as more than an exit code: the token file
must not exist afterwards. A non-zero exit that still wrote the file would leave a
consumable authorisation behind, which is a warning wearing a refusal's clothes.

RED state: ``approve_command`` reads no issue state, so both mints exit 0 and both
files appear — the defect, reproduced.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.approval_paths import approval_token_path
from atdd.coach.gate.approve_command import run as run_approve
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform]

# Never a live issue: the repo's issues are in the low thousands.
_ISSUE = 999735
_UID = "mint-does-not-check-the-edge-is-reachable-integration-001"
_BRANCH = "feat/mint-does-not-check-the-edge-is-reachable"

#: The two edges #1726 got tokens for while standing at INIT.
_ORPHANED_EDGES = (("PLANNED", "RED"), ("SMOKE", "REFACTOR"))


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated Control Root, so no live issue and no real store is touched."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    monkeypatch.setenv("ATDD_APPROVAL_SIGNING_KEY", "integration-operator-key")
    return tmp_path


def _register(repo: Path, state: str | None) -> None:
    with open_state_store(control_root=repo) as store:
        store.objects.upsert(_UID, "work_item", state=state, data={"branch": _BRANCH})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def _mint(repo: Path, from_phase: str, to_phase: str) -> int:
    return run_approve(
        [str(_ISSUE), "--transition", f"{from_phase}->{to_phase}", "--by", "operator"],
        target_dir=repo,
        env={"USER": "operator"},
    )


@pytest.mark.parametrize(("from_phase", "to_phase"), _ORPHANED_EDGES)
def test_the_two_edges_1726_got_tokens_for_are_refused_at_init(
    repo: Path, from_phase: str, to_phase: str
) -> None:
    """An issue at INIT cannot be approved for an edge further down the lifecycle."""
    _register(repo, "INIT")

    assert _mint(repo, from_phase, to_phase) == 1, (
        f"the mint accepted {from_phase}->{to_phase} for an issue at INIT — this is "
        f"the #1726 reproduction, unchanged"
    )


@pytest.mark.parametrize(("from_phase", "to_phase"), _ORPHANED_EDGES)
def test_no_token_file_is_left_behind(
    repo: Path, from_phase: str, to_phase: str
) -> None:
    """A written token is consumable; the refusal must leave nothing on disk."""
    _register(repo, "INIT")
    _mint(repo, from_phase, to_phase)

    path = approval_token_path(repo, _ISSUE, from_phase, to_phase)
    assert not path.exists(), f"a refused mint still wrote {path}"
    # Not even the directory: the mkdir used to happen before anything was checked,
    # so an approvals/ dir appearing here would mean the refusal landed after the
    # side effects rather than before them.
    assert not path.parent.exists(), (
        f"a refused mint created the approvals directory at {path.parent}"
    )


def test_the_refusal_names_the_phase_the_issue_is_actually_on(repo: Path, capsys) -> None:
    """Without this the operator cannot act on the refusal.

    "PLANNED->RED refused" leaves two possibilities — approve a different edge, or
    advance the issue — and no way to choose between them. Naming INIT settles it.
    """
    _register(repo, "INIT")

    _mint(repo, "PLANNED", "RED")

    out = capsys.readouterr().out
    assert "INIT" in out, (
        f"the refusal does not name the phase the issue is standing on: {out!r}"
    )
    # And the way forward, so the next move is in the message rather than in the
    # convention file.
    assert "PLANNED" in out, out


def test_an_unregistered_issue_is_refused_rather_than_waved_through(repo: Path) -> None:
    """Fail-closed on the lookup, as SmokeExecutionGateCheck is for the same one.

    An issue the store cannot resolve is the case where the mint knows least, so it
    is the case where minting anyway would be worst.
    """
    assert _mint(repo, "PLANNED", "RED") == 1
    assert not approval_token_path(repo, _ISSUE, "PLANNED", "RED").exists()


def test_a_work_item_with_no_recorded_phase_is_refused(repo: Path) -> None:
    """"I could not observe a phase" is not "any phase will do"."""
    _register(repo, None)

    assert _mint(repo, "PLANNED", "RED") == 1
    assert not approval_token_path(repo, _ISSUE, "PLANNED", "RED").exists()
