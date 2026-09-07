# URN: test:govern-lifecycle:operator-approval-token-gate:C021-UNIT-001-a-refusing-check-refuses-the-mint-and-leaves-no-token
# Acceptance: acc:govern-lifecycle:C021-UNIT-001-a-refusing-check-refuses-the-mint-and-leaves-no-token
# WMBT: wmbt:govern-lifecycle:C021
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C021-UNIT-001 — a check that refuses the transition refuses the mint.

``atdd coach approve`` parsed, signed and wrote. It consulted ``GATE_REGISTRY``
at no point, so the artifact the enforcing gate later accepts as authorisation
was produced without evaluating a single check that gate will run.

This file holds the central claim of #1670 slice C: on ``SMOKE->REFACTOR`` the
mint runs the edge's substantive checks first, and both of #1719's blocking
verdicts stop it. ``COULD_NOT_CHECK`` is the one that matters most — an
authorisation bought by "I could not look" is the defect one level up from the
one the verdict was introduced to remove.

AND IT MUST LEAVE NOTHING BEHIND. A refusal announced after the file exists is
not a refusal: ``ApprovalTokenGateCheck`` reads the filesystem and will accept
that token whatever the mint printed. So the assertion is the ABSENCE of an
artifact, not the presence of a message.

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
from atdd.coach.gate.registry import GateRegistry
from atdd.coach.gate.mint_gate import decide_mint

pytestmark = [pytest.mark.platform]

_RULE = "repo.govern-lifecycle.c021"
_ISSUE = 999021
_UID = "c021-unit-001-refusing-check"
_BRANCH = "feat/token-proves-gates-passed"


@dataclass(frozen=True)
class _ScriptedCheck:
    """A substantive check whose verdict the test dictates.

    Deliberately NOT ``SmokeExecutionGateCheck``: this acceptance is about what
    the mint does with a verdict, and pinning it to the one check that produces
    verdicts today would make the test fail for reasons that belong to #1602.
    The real check is exercised end-to-end in C021-SMOKE-001.
    """

    verdict: GateVerdict
    gate_id: str = "GT-SUBSTANTIVE"
    rule_id: str = _RULE

    def run(self, ctx: GateContext) -> GateCheckResult:
        builder = {
            GateVerdict.PASS: GateCheckResult.passing,
            GateVerdict.FAIL: GateCheckResult.failing,
            GateVerdict.COULD_NOT_CHECK: GateCheckResult.could_not_check,
            GateVerdict.NOT_APPLICABLE: GateCheckResult.not_applicable,
        }[self.verdict]
        return builder(self.gate_id, self.rule_id, f"scripted {self.verdict.value}")


def _registry(*checks) -> GateRegistry:
    registry = GateRegistry()
    for check in checks:
        registry.register("SMOKE", "REFACTOR", check)
    return registry


def _gated_worktree(tmp_path: Path) -> Path:
    """A real git worktree whose config gates SMOKE->REFACTOR, as this repo's does.

    Genuinely ``git init``-ed with a commit, because the mint refuses when it
    cannot resolve HEAD (C021-UNIT-004) — a mint writes an authorisation for a
    tree, and it cannot certify anything about a tree it cannot name. Faking
    that away here would test the mint against a precondition it does not have.

    It also seeds the branch binding #1721 requires — see :func:`_bind_issue` —
    and CHECKS THAT BRANCH OUT, because since #1765 the mint resolves the commit
    it certifies from that binding rather than from ``HEAD`` in this directory. A
    checkout carrying the binding but not the branch would refuse for #1765's
    reason and prove nothing about the check verdicts this file is about.
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

    #1721 merged after this file was written and added a precondition ahead of
    the gate run: a mint refuses outright for an issue the store binds to no
    branch. Without this the tests below would refuse for #1721's reason and pass
    for the wrong one — the vacuous green this whole slice exists to remove.

    Real state, not a bypass, following the pattern #1721 established in
    ``test_c012_unit_001``: a test-only escape on the mint would be a second
    ungated way to mint (#1619), inside a file whose subject is the mint refusing.
    """
    from atdd.state.smoke_evidence import open_state_store

    with open_state_store(control_root=root) as store:
        store.objects.upsert(
            _UID, "work_item", state="SMOKE", data={"branch": _BRANCH}
        )
        store.external_refs.link(_UID, "github", "issue", str(_ISSUE))


def _decide(worktree: Path, registry: GateRegistry):
    # registrars=() because this test supplies its own registry; the real pair is
    # asserted to be invoked in C021-UNIT-003.
    return decide_mint(
        worktree, _ISSUE, "SMOKE", "REFACTOR", registry=registry, registrars=()
    )


def test_a_failing_check_refuses_the_mint(tmp_path):
    """FAIL blocks the transition, so it must block the receipt for it."""
    worktree = _gated_worktree(tmp_path)
    decision = _decide(worktree, _registry(_ScriptedCheck(GateVerdict.FAIL)))

    assert decision.proceed is False, (
        "a check that observed a violation still authorised the mint — the token "
        "would then satisfy the very gate that refused"
    )


def test_a_could_not_check_verdict_refuses_the_mint(tmp_path):
    """"I could not look" must not buy what "I looked and it was fine" buys."""
    worktree = _gated_worktree(tmp_path)
    decision = _decide(worktree, _registry(_ScriptedCheck(GateVerdict.COULD_NOT_CHECK)))

    assert decision.proceed is False, (
        "an unmade observation authorised a signed approval; this is #1719's "
        "defect reappearing on the mint surface"
    )


def test_the_two_refusals_are_reported_apart(tmp_path):
    """Identical in effect, distinct in remedy — so distinct in the report.

    "Your smoke did not pass" and "I could not read the store" send the operator
    to different places, and a merged blocker list destroys that.
    """
    worktree = _gated_worktree(tmp_path)
    registry = _registry(
        _ScriptedCheck(GateVerdict.FAIL, gate_id="GT-BROKEN"),
        _ScriptedCheck(GateVerdict.COULD_NOT_CHECK, gate_id="GT-BLIND"),
    )
    decision = _decide(worktree, registry)

    assert decision.proceed is False
    assert [r.gate_id for r in decision.outcome.failures] == ["GT-BROKEN"]
    assert [r.gate_id for r in decision.outcome.unobservable] == ["GT-BLIND"]
    assert len(decision.outcome.blockers) == 2, (
        "the rendered blocker set must be the union; counting only `failures` "
        "reports a mint blocked solely by an unobservable check as blocked by nothing"
    )


def test_one_refusing_check_is_enough_even_beside_passing_ones(tmp_path):
    """AND-semantics, not majority — the same rule C007 gave the gate."""
    worktree = _gated_worktree(tmp_path)
    registry = _registry(
        _ScriptedCheck(GateVerdict.PASS, gate_id="GT-A"),
        _ScriptedCheck(GateVerdict.COULD_NOT_CHECK, gate_id="GT-B"),
        _ScriptedCheck(GateVerdict.PASS, gate_id="GT-C"),
    )

    assert _decide(worktree, registry).proceed is False


def test_a_refused_mint_writes_no_token_file(tmp_path, monkeypatch):
    """The refusal is the absence of an artifact, not a message about one.

    Driven through the real ``approve_command.run`` rather than ``decide_mint``,
    because the thing under test is that the command returns before it creates
    the file — a mint that writes and then complains has authorised the
    transition regardless of its exit code.
    """
    from atdd.coach.gate import approve_command, mint_gate

    worktree = _gated_worktree(tmp_path)
    monkeypatch.setattr(
        mint_gate, "GATE_REGISTRY", _registry(_ScriptedCheck(GateVerdict.FAIL))
    )
    monkeypatch.setattr(mint_gate, "DEFAULT_REGISTRARS", ())

    rc = approve_command.run(
        [str(_ISSUE), "--transition", "SMOKE->REFACTOR"], target_dir=worktree, env={}
    )

    assert rc != 0, "a refused mint must exit non-zero"
    token_path = approval_token_path(worktree, _ISSUE, "SMOKE", "REFACTOR")
    assert not token_path.exists(), (
        f"the mint was refused but wrote {token_path} anyway — "
        f"ApprovalTokenGateCheck reads the filesystem, so this token authorises "
        f"the transition no matter what the command printed"
    )
    assert not list(worktree.rglob("SMOKE-REFACTOR.json")), (
        "no token for this transition may exist anywhere under the root, "
        "including the worktree-local back-compat path the gate still honours"
    )


def test_a_passing_check_still_mints(tmp_path, monkeypatch):
    """The discriminating control: the refusal is the verdict, not the feature.

    Without this, a conditional mint that refused unconditionally would satisfy
    every other assertion in this file.
    """
    from atdd.coach.gate import approve_command, mint_gate

    worktree = _gated_worktree(tmp_path)
    monkeypatch.setattr(
        mint_gate, "GATE_REGISTRY", _registry(_ScriptedCheck(GateVerdict.PASS))
    )
    monkeypatch.setattr(mint_gate, "DEFAULT_REGISTRARS", ())

    rc = approve_command.run(
        [str(_ISSUE), "--transition", "SMOKE->REFACTOR"], target_dir=worktree, env={}
    )

    assert rc == 0
    token_path = approval_token_path(worktree, _ISSUE, "SMOKE", "REFACTOR")
    assert token_path.exists(), "a mint whose checks passed must still write the token"
    token = json.loads(token_path.read_text())
    assert token["from_phase"] == "SMOKE" and token["to_phase"] == "REFACTOR"
