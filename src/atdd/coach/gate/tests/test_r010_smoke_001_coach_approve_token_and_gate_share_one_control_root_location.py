# URN: test:govern-lifecycle:operator-approval-token-gate:R010-SMOKE-001-coach-approve-token-and-gate-share-one-control-root-location
# Acceptance: acc:govern-lifecycle:R010-SMOKE-001-coach-approve-token-and-gate-share-one-control-root-location
# WMBT: wmbt:govern-lifecycle:R010
# Phase: SMOKE
# Layer: integration
# Smoke: true
# Assertion: behavioral
# Purpose: drive the REAL mint (approve_command.run) and the REAL gate (registrations -> registry -> evaluate_transition_gate) against one temp Control Root, proving both ends resolve the token to the same place
"""R010-SMOKE-001 — mint and check resolve the token to ONE shared location.

No fakes on either end. The real ``atdd coach approve`` (``approve_command.run``)
writes the token; the real ``register_approval_checks`` registers the real
``ApprovalTokenGateCheck``; the real ``evaluate_transition_gate`` decides. The
operator stands in the CHILD worktree and the gate evaluates from the CHILD
worktree, and the token must nonetheless land at — and be read from — the shared
Control Root above them both.

This is the property #1670 needs: a receipt whose location resolves identically
at mint and at check. The test fails if the two ends ever diverge again, in
EITHER direction (token minted where the gate cannot see it, or read from a
worktree it was not minted for).

Hermetic: a temp Control Root under ``tmp_path`` and a THROWAWAY issue number
that is not any real issue. No GitHub call, no label write, no live Control Root
touched — the gate reads the filesystem, never the cmux Feed.

RED state: ``approve_command`` writes to ``target_dir or Path.cwd()`` and
``approval_check`` reads ``ctx.worktree / rel``, so both anchor on the child and
the shared Control Root is never involved.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.gate.approval import approval_relpath
from atdd.coach.gate.approval_paths import approval_control_root
from atdd.coach.gate.approve_command import run as run_approve
from atdd.coach.gate.decision import GateContext, evaluate_transition_gate
from atdd.coach.gate.registrations import register_approval_checks
from atdd.coach.gate.registry import GateRegistry
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform, pytest.mark.smoke]

# Never a live issue: the repo's issues are in the low thousands.
_ISSUE, _FROM, _TO = 999999, "PLANNED", "RED"
_GATED_CONFIG = {"gate": {"transitions": {f"{_FROM}->{_TO}": True}}}
_UID = "r010-smoke-001-one-control-root-location"
_BRANCH = "feat/r010-approval-token-control-root"


def _seed_mintable_issue(control_root: Path) -> None:
    """Both of the mint's preconditions, seeded at the CONTROL ROOT.

    #1721 made the branch binding a precondition: the token is bound to the branch
    the State Store binds the issue to, and the mint refuses rather than writing an
    unbound one — hence ``data["branch"]``. #1735 made the issue's phase one too:
    the mint refuses an edge the issue is not standing on — hence ``state``.

    Seeded at the CONTROL ROOT, which is this file's whole subject: the mint and the
    gate resolve the store from the same base they resolve the token path from, so a
    work item written here is the one both ends read, no matter which worktree the
    operator stands in.
    """
    with open_state_store(control_root=control_root) as store:
        store.objects.upsert(_UID, "work_item", state=_FROM, data={"branch": _BRANCH})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


@pytest.fixture
def nested_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A temp Control Root with a child worktree nested beneath it."""
    control_root = tmp_path / "project"
    (control_root / ".atdd" / "state").mkdir(parents=True)
    child = control_root / "feat-some-worktree"
    child.mkdir()
    assert approval_control_root(child) == control_root.resolve()
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(control_root.resolve()))
    _seed_mintable_issue(control_root.resolve())
    return control_root.resolve(), child


def _ctx(worktree: Path) -> GateContext:
    return GateContext(
        issue_number=_ISSUE, from_phase=_FROM, to_phase=_TO, worktree=worktree
    )


def test_real_approve_and_real_gate_share_one_control_root_location(
    nested_worktree, monkeypatch
):
    """R010-SMOKE-001: one location, no per-worktree divergence."""
    monkeypatch.setenv("ATDD_APPROVAL_SIGNING_KEY", "smoke-operator-key")
    control_root, child = nested_worktree
    registry = GateRegistry()
    register_approval_checks(registry)  # real production registration

    # 1) No token yet -> the real gate BLOCKS from the child worktree.
    blocked = evaluate_transition_gate(registry, _GATED_CONFIG, _ctx(child))
    assert blocked.proceed is False
    assert any(f.gate_id == "approval-token" for f in blocked.failures)

    # 2) The real operator command runs FROM THE CHILD WORKTREE...
    rc = run_approve(
        [str(_ISSUE), "--transition", f"{_FROM}->{_TO}", "--by", "operator"],
        target_dir=child,
    )
    assert rc == 0

    # ...and the token lands at the SHARED Control Root, not under the child.
    rel = approval_relpath(_ISSUE, _FROM, _TO)
    assert (control_root / rel).exists()
    assert not (child / rel).exists()

    # 3) The real gate, still evaluating from the child, reads that same token.
    proceeded = evaluate_transition_gate(registry, _GATED_CONFIG, _ctx(child))
    assert proceeded.proceed is True

    # 4) A SIBLING worktree of the same project reads the same receipt — the
    #    thing that was impossible before #1376.
    sibling = control_root / "feat-another-worktree"
    sibling.mkdir()
    assert evaluate_transition_gate(registry, _GATED_CONFIG, _ctx(sibling)).proceed is True

    # 5) Scope isolation still holds on the real path: the PLANNED->RED receipt
    #    does not unlock RED->GREEN.
    next_ctx = GateContext(
        issue_number=_ISSUE, from_phase="RED", to_phase="GREEN", worktree=child
    )
    next_gated = {"gate": {"transitions": {"RED->GREEN": True}}}
    assert evaluate_transition_gate(registry, next_gated, next_ctx).proceed is False


def test_single_repo_layout_is_unchanged(tmp_path: Path, monkeypatch):
    """A worktree that IS its own Control Root mints and checks in place.

    Guards the degrade path: when no Control Root resolves above the worktree,
    ``approval_control_root`` answers with the worktree itself, so single-repo
    checkouts and consumer repos behave exactly as they did before #1376.
    """
    monkeypatch.setenv("ATDD_APPROVAL_SIGNING_KEY", "smoke-operator-key")
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    _seed_mintable_issue(tmp_path)
    registry = GateRegistry()
    register_approval_checks(registry)

    rc = run_approve(
        [str(_ISSUE), "--transition", f"{_FROM}->{_TO}", "--by", "operator"],
        target_dir=tmp_path,
    )
    assert rc == 0
    assert (tmp_path / approval_relpath(_ISSUE, _FROM, _TO)).exists()
    assert evaluate_transition_gate(registry, _GATED_CONFIG, _ctx(tmp_path)).proceed is True
