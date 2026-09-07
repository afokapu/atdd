# URN: test:govern-lifecycle:operator-approval-token-gate:C021-UNIT-002-not-applicable-mints-and-the-report-does-not-call-it-a-pass
# Acceptance: acc:govern-lifecycle:C021-UNIT-002-not-applicable-mints-and-the-report-does-not-call-it-a-pass
# WMBT: wmbt:govern-lifecycle:C021
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C021-UNIT-002 — NOT_APPLICABLE mints, and the report does not call it a pass.

THE SINGLE EASIEST WAY TO BREAK THIS REPO. ``SmokeExecutionGateCheck`` is opt-in
per issue: it reports ``NOT_APPLICABLE`` for any issue whose plan declares no
``execution_kind: live_smoke`` acceptance — 787 of 787 work items when the edge
was enabled in ``.atdd/config.yaml``. A conditional mint that refused on that
verdict would strand every one of them at SMOKE with ``--force`` as the only
exit, which is the rubber-stamp failure the opt-in exists to prevent, rebuilt by
the fix.

THE SECOND EASIEST. Proceeding but *reporting* it as a verified pass. The mint
would then print "gates passed" over a run in which nothing was verified — the
vacuous green this program exists to remove, reinstated one layer up in the
sentence the operator actually reads. So the report must separate checks that
verified an obligation from checks that established none was owed, and the PASS
case is here as the discriminator: if both render identically, the distinction
is decorative.

RED state: ``atdd.coach.gate.mint_gate`` does not exist.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from atdd.coach.gate.approval_paths import approval_token_path
from atdd.coach.gate.decision import GateCheckResult, GateContext, GateVerdict
from atdd.coach.gate.mint_gate import decide_mint
from atdd.coach.gate.registry import GateRegistry

pytestmark = [pytest.mark.platform]

_RULE = "repo.govern-lifecycle.c021"
_ISSUE = 999022
_UID = "c021-unit-002-not-applicable"
_BRANCH = "feat/token-proves-gates-passed"

#: The PLANNED->RED control below needs an issue STANDING at PLANNED, which is a
#: second work item rather than a second edge on the first: #1735 refuses a mint
#: for an edge the issue is not on, and :data:`_ISSUE` is at SMOKE because that is
#: the edge this file's subject covers. One work item cannot be both, so the
#: control gets its own — see :func:`_bind_the_planned_control`.
_PLANNED_ISSUE = 999023
_PLANNED_UID = "c021-unit-002-planned-control"


@dataclass(frozen=True)
class _ScriptedCheck:
    """A substantive check whose verdict the test dictates."""

    verdict: GateVerdict
    gate_id: str = "GT-SUBSTANTIVE"
    rule_id: str = _RULE

    def run(self, ctx: GateContext) -> GateCheckResult:
        builder = {
            GateVerdict.PASS: GateCheckResult.passing,
            GateVerdict.NOT_APPLICABLE: GateCheckResult.not_applicable,
        }[self.verdict]
        return builder(self.gate_id, self.rule_id, f"scripted {self.verdict.value}")


def _worktree(tmp_path: Path) -> Path:
    """The issue's OWN worktree: bound to :data:`_BRANCH` and standing on it.

    The checkout step arrived with #1765. The mint now resolves the commit it
    certifies from the issue's branch binding rather than from ``HEAD`` here, so a
    repo that carries the binding but not the branch refuses before any check runs
    — and the NOT_APPLICABLE safety property this file exists to hold would then
    be asserted against a refusal for an unrelated reason.
    """
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "gate:\n  transitions:\n    SMOKE->REFACTOR: true\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit",
         "-q", "--allow-empty", "-m", "root"],
        cwd=tmp_path, check=True,
    )
    subprocess.run(["git", "checkout", "-q", "-b", _BRANCH], cwd=tmp_path, check=True)
    _bind_issue(tmp_path)
    return tmp_path


def _bind_issue(root: Path) -> None:
    """Seed the State Store branch binding the mint requires (#1721).

    #1721 merged after this file was written and added a precondition ahead of the
    gate run: a mint refuses outright for an issue the store binds to no branch.
    Without this the tests below would refuse for #1721's reason and pass for the
    wrong one — the vacuous green this whole slice exists to remove.

    Real state, not a bypass, following the pattern #1721 established in
    ``test_c012_unit_001``: a test-only escape on the mint would be a second
    ungated way to mint (#1619), inside a file whose subject is the mint refusing.
    """
    from atdd.state.smoke_evidence import open_state_store

    with open_state_store(control_root=root) as store:
        store.objects.upsert(_UID, "work_item", state="SMOKE", data={"branch": _BRANCH})
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def _bind_the_planned_control(root: Path) -> None:
    """Seed a SECOND work item, standing at PLANNED, for the unconditional-edge control.

    #1735 merged after this file was written and refuses to mint for an edge the
    issue is not standing on. The two PLANNED->RED assertions below were written
    against :data:`_ISSUE`, which sits at SMOKE — so after #1735 they were refused
    with "is at SMOKE, not PLANNED" and proved nothing about the unconditional
    edge. That check is right and the fixture was stale.

    The control cannot be dropped: it is what proves slice C is scoped to
    SMOKE->REFACTOR alone. So it gets an issue actually standing at PLANNED —
    real state, in the same store, seeded the same way — rather than a relaxed
    precondition or a bypass, either of which would be a second ungated way to
    mint (#1619) inside a file about the mint refusing.
    """
    from atdd.state.smoke_evidence import open_state_store

    with open_state_store(control_root=root) as store:
        store.objects.upsert(
            _PLANNED_UID, "work_item", state="PLANNED", data={"branch": _BRANCH}
        )
        store.external_refs.link(_PLANNED_UID, "github", "issue", str(_PLANNED_ISSUE))


def _decide(worktree: Path, verdict: GateVerdict):
    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", _ScriptedCheck(verdict))
    return decide_mint(
        worktree, _ISSUE, "SMOKE", "REFACTOR", registry=registry, registrars=()
    )


def test_not_applicable_proceeds_so_no_issue_is_stranded(tmp_path):
    """The safety property, stated first because it is the one that breaks the repo."""
    decision = _decide(_worktree(tmp_path), GateVerdict.NOT_APPLICABLE)

    assert decision.proceed is True, (
        "the mint refused an issue that owes no live smoke — this strands every "
        "issue declaring no live_smoke acceptance at SMOKE behind --force, which "
        "was 787 of 787 work items when the edge was enabled"
    )


def test_the_report_states_zero_verified_when_nothing_was_owed(tmp_path):
    """Proceeding is not the same as having verified something, and must not read as it."""
    decision = _decide(_worktree(tmp_path), GateVerdict.NOT_APPLICABLE)

    assert decision.coverage.evaluated == 1
    assert decision.coverage.verified == 0, (
        "a check that established no obligation was counted as one that verified "
        "an obligation — this is the vacuous green re-entering through the report"
    )
    assert decision.coverage.none_owed == 1


def test_a_verified_pass_renders_differently_from_nothing_owed(tmp_path):
    """The discriminator: if the two render alike, the distinction is decorative."""
    worktree = _worktree(tmp_path)
    none_owed = _decide(worktree, GateVerdict.NOT_APPLICABLE).render()
    verified = _decide(worktree, GateVerdict.PASS).render()

    assert none_owed != verified, (
        "'one check verified an obligation' and 'one check found none was owed' "
        "produced the same operator-facing text"
    )
    assert "0 verified" in none_owed or "verified an obligation: 0" in none_owed


def test_a_verified_pass_counts_as_verified(tmp_path):
    """The other half of the same split, so neither side can absorb the other."""
    decision = _decide(_worktree(tmp_path), GateVerdict.PASS)

    assert decision.proceed is True
    assert decision.coverage.verified == 1
    assert decision.coverage.none_owed == 0


def test_the_command_says_what_it_certified_on_the_success_path(tmp_path, monkeypatch, capsys):
    """A bare ✓ reads the same whether anything was verified or not.

    ``decide_mint`` distinguishing the two is worth nothing if the command
    prints neither. This is the assertion that the distinction reaches the
    operator rather than living in a dataclass.
    """
    from atdd.coach.gate import approve_command, mint_gate

    worktree = _worktree(tmp_path)
    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", _ScriptedCheck(GateVerdict.NOT_APPLICABLE))
    monkeypatch.setattr(mint_gate, "GATE_REGISTRY", registry)
    monkeypatch.setattr(mint_gate, "DEFAULT_REGISTRARS", ())

    approve_command.run(
        [str(_ISSUE), "--transition", "SMOKE->REFACTOR"], target_dir=worktree, env={}
    )
    out = capsys.readouterr().out

    assert "verified an obligation: 0" in out, (
        f"the mint printed a bare success over a run that verified nothing:\n{out}"
    )
    assert "found none owed: 1" in out


def test_an_unconditional_edge_does_not_claim_gate_coverage(tmp_path, monkeypatch, capsys):
    """PLANNED->RED runs no checks, so it must not print a coverage line.

    Printing one would be the mirror-image dishonesty: a mint that certified
    nothing describing itself as though it had.

    Minted for :data:`_PLANNED_ISSUE`, not :data:`_ISSUE`: since #1735 an issue
    only mints the edge it is standing on, and this control is about PLANNED->RED.
    """
    from atdd.coach.gate import approve_command, mint_gate

    worktree = _worktree(tmp_path)
    _bind_the_planned_control(worktree)
    monkeypatch.setattr(mint_gate, "GATE_REGISTRY", GateRegistry())
    monkeypatch.setattr(mint_gate, "DEFAULT_REGISTRARS", ())

    assert approve_command.run(
        [str(_PLANNED_ISSUE), "--transition", "PLANNED->RED"], target_dir=worktree, env={}
    ) == 0
    out = capsys.readouterr().out

    assert "gate coverage" not in out
    assert "✓ approved PLANNED->RED" in out


def test_the_token_written_under_not_applicable_is_the_ordinary_token(tmp_path, monkeypatch):
    """Proceeding here must change nothing downstream.

    The token is the artifact ``ApprovalTokenGateCheck`` verifies; if the
    conditional path wrote a differently-shaped one, every issue owing no live
    smoke would mint a receipt the gate then rejects — stranding by another route.
    """
    from atdd.coach.gate import approve_command, mint_gate

    worktree = _worktree(tmp_path)
    _bind_the_planned_control(worktree)
    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", _ScriptedCheck(GateVerdict.NOT_APPLICABLE))
    monkeypatch.setattr(mint_gate, "GATE_REGISTRY", registry)
    monkeypatch.setattr(mint_gate, "DEFAULT_REGISTRARS", ())

    rc = approve_command.run(
        [str(_ISSUE), "--transition", "SMOKE->REFACTOR"], target_dir=worktree, env={}
    )

    assert rc == 0
    token = json.loads(
        approval_token_path(worktree, _ISSUE, "SMOKE", "REFACTOR").read_text()
    )
    # Compared against a PLANNED->RED token from the same command, which takes the
    # unconditional path — so any field the conditional path added or dropped shows
    # up as a key difference rather than having to be enumerated here. The baseline
    # is minted for _PLANNED_ISSUE because since #1735 only an issue standing at
    # PLANNED can mint that edge; the comparison is over KEYS, so a second issue
    # number changes nothing about what is being asserted.
    assert approve_command.run(
        [str(_PLANNED_ISSUE), "--transition", "PLANNED->RED"], target_dir=worktree, env={}
    ) == 0
    baseline = json.loads(
        approval_token_path(worktree, _PLANNED_ISSUE, "PLANNED", "RED").read_text()
    )
    assert set(token) == set(baseline), (
        "the conditionally-minted token has a different shape from an ordinary "
        "one; ApprovalTokenGateCheck verifies a fixed scope and would reject it"
    )
