# URN: test:govern-lifecycle:operator-approval-token-gate:C021-UNIT-004-an-unresolvable-head-refuses-the-mint
# Acceptance: acc:govern-lifecycle:C021-UNIT-004-an-unresolvable-head-refuses-the-mint
# WMBT: wmbt:govern-lifecycle:C021
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C021-UNIT-004 — a tree the mint cannot name is a tree it cannot certify.

``SmokeExecutionGateCheck._head_sha`` returns ``None`` when git is silent, and
``evaluate_smoke_execution`` then disables its staleness clause ENTIRELY. That is
deliberate and, for a gate, defensible — its own docstring argues it: *"an
unresolvable HEAD is an environment fault, and turning it into 'smoke did not
run' would make the gate unfixable rather than fail-closed."*

Under a MINT the same permissiveness reads differently. The attestation's binding
to the tree is silently switched off and a signed authorisation is written
anyway — "I could not look at whether this evidence is stale" passing as "the
evidence is current". That is #1670's condition 3 in the one place it is easiest
to miss, because nothing fails and no message appears.

THE CHECK IS NOT MODIFIED TO OBTAIN THIS. It is not this issue's to change, and
changing it would alter ``atdd coach transition``'s behaviour repo-wide for every
issue. The mint asks the question itself instead: strictness is added where the
authorisation is written, and the transition gate keeps the permissiveness its
own docstring argues for.

RED state: ``atdd.coach.gate.mint_gate`` does not exist.
"""
from __future__ import annotations

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
_ISSUE = 999024


@dataclass(frozen=True)
class _AlwaysPasses:
    """A substantive check that would authorise the mint if it were reached."""

    gate_id: str = "GT-SUBSTANTIVE"
    rule_id: str = _RULE

    def run(self, ctx: GateContext) -> GateCheckResult:
        return GateCheckResult.passing(self.gate_id, self.rule_id, "observed, satisfied")


def _config(root: Path) -> Path:
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "config.yaml").write_text(
        "gate:\n  transitions:\n    SMOKE->REFACTOR: true\n"
    )
    return root


def _headless(tmp_path: Path) -> Path:
    """A directory that is not a git checkout, so HEAD cannot be resolved."""
    return _config(tmp_path / "headless")


def _with_head(tmp_path: Path) -> Path:
    root = _config(tmp_path / "checkout")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit",
         "-q", "--allow-empty", "-m", "root"],
        cwd=root, check=True,
    )
    return root


def _decide(worktree: Path):
    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", _AlwaysPasses())
    return decide_mint(
        worktree, _ISSUE, "SMOKE", "REFACTOR", registry=registry, registrars=()
    )


def test_an_unresolvable_head_refuses_the_mint(tmp_path):
    """The check would have passed; the mint refuses anyway."""
    decision = _decide(_headless(tmp_path))

    assert decision.proceed is False, (
        "a signed authorisation was written for a tree the mint could not "
        "identify — the attestation's staleness clause is disabled in exactly "
        "this state, so nothing verified that the evidence matched the code"
    )
    assert decision.verdict is GateVerdict.COULD_NOT_CHECK, (
        "an unresolvable HEAD is an unmade observation, not an observed violation"
    )


def test_the_refusal_says_the_staleness_of_the_evidence_is_unestablished(tmp_path):
    """Name the cause, or the operator cannot act on the refusal."""
    rendered = _decide(_headless(tmp_path)).render().lower()

    assert "head" in rendered
    assert "stale" in rendered or "current" in rendered


def test_a_resolvable_head_mints(tmp_path):
    """The discriminating control: the refusal is the headless tree, not the check.

    Without this leg a precondition that refused unconditionally would satisfy
    every other assertion in this file.
    """
    decision = _decide(_with_head(tmp_path))

    assert decision.proceed is True
    assert decision.verdict is not GateVerdict.COULD_NOT_CHECK


def test_the_smoke_execution_check_is_left_permissive(tmp_path):
    """Strictness is added at the mint, not taken out of the transition gate.

    ``evaluate_smoke_execution`` must still ignore staleness on ``head_sha=None``.
    If a later change tightens it there, ``atdd coach transition`` starts refusing
    every issue in a non-git environment — a repo-wide behaviour change this
    acceptance explicitly does not authorise.
    """
    from atdd.state.smoke_evidence import SmokeRun, evaluate_smoke_execution

    runs = [SmokeRun(nodeid="t", outcome="passed", duration_s=1.0, commit_sha="deadbeef")]

    assert evaluate_smoke_execution(runs, head_sha=None).satisfied is True, (
        "the gate's deliberate permissiveness on an unresolvable HEAD was removed; "
        "that is #1602's decision to change, not this one's"
    )
    assert evaluate_smoke_execution(runs, head_sha="0" * 40).satisfied is False


def test_a_headless_refusal_writes_no_token(tmp_path, monkeypatch):
    """Same rule as every other refusal: the absence of an artifact is the refusal."""
    from atdd.coach.gate import approve_command, mint_gate

    worktree = _headless(tmp_path)
    registry = GateRegistry()
    registry.register("SMOKE", "REFACTOR", _AlwaysPasses())
    monkeypatch.setattr(mint_gate, "GATE_REGISTRY", registry)
    monkeypatch.setattr(mint_gate, "DEFAULT_REGISTRARS", ())

    rc = approve_command.run(
        [str(_ISSUE), "--transition", "SMOKE->REFACTOR"], target_dir=worktree, env={}
    )

    assert rc != 0
    assert not approval_token_path(worktree, _ISSUE, "SMOKE", "REFACTOR").exists()
