# Phase: SPIKE
# Layer: integration
# Assertion: behavioral
"""#1602 — the smoke-execution gate is fail-closed, both directions.

This file began as the spike's deliverable, when the attestation it read was a
hand-placed JSON fixture. The fixture is gone: every case below now records (or
declines to record) through the REAL producer API,
``atdd.state.evidence.record_smoke_execution``, against a real migrated State
Store. The assertions are unchanged — which is the point of keeping the file:
the behaviour the spike proved against a stub must still hold now that the stub
is a store.

A green result that cannot distinguish "smoke ran" from "smoke didn't" would be
worth nothing — that is the exact bug class this whole audit exists to close —
so all three fault injections run against the REAL transition path
(``IssueLifecycle.transition`` -> ``apply_transition`` -> ``_transition_gate``),
and "did not occur" is proven behaviorally via a recording spy on
``IssueManager.update`` (the label/phase swap), never by scraping stdout.

    1. no attestation        -> transition BLOCKED   (the bug being closed)
    2. passing attestation   -> transition PROCEEDS  (the negative control —
                                without this, blocking everything would "pass")
    3. check raises          -> transition BLOCKED   (fail-closed inheritance)

EVERY CASE HERE IS AN OBLIGATED ISSUE. The gate is opt-in per issue (#1602
Convergence A): it holds an issue to a live-smoke run only when that issue's own
plan scope declares an ``execution_kind: live_smoke`` acceptance. So the fixture
worktree writes that declaration and binds the work item to it — otherwise every
row below would pass as *not applicable* and this file would assert nothing about
fail-closed at all. The opposite case (an issue that declares none) is proven in
``test_1602_smoke_gate_is_opt_in_per_issue.py``, where it belongs.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from unittest.mock import MagicMock, patch

from atdd.coach.commands.issue_lifecycle import IssueLifecycle
from atdd.coach.gate.live_smoke import write_live_smoke_plan_scope
from atdd.coach.gate.approve_command import run as run_approve
from atdd.coach.gate.registrations import register_smoke_execution_check
from atdd.coach.gate.registry import GATE_REGISTRY
from atdd.coach.gate.smoke_execution_check import GATE_ID, SmokeExecutionGateCheck
from atdd.state.smoke_evidence import SmokeRun, open_state_store, record_smoke_execution

pytestmark = [pytest.mark.platform]

ISSUE = 1602
UID = "smoke-execution-gate-wiring"

# The one config line that turns enforcement on (proposal edit 4). Supplied by
# the test rather than committed to .atdd/config.yaml — this proves the
# mechanism without switching the repo's own SMOKE->REFACTOR gate on.
GATED_CONFIG = {"gate": {"transitions": {"SMOKE->REFACTOR": True}}}


@pytest.fixture
def smoke_issue():
    """An issue sitting in SMOKE, so from_phase resolves to SMOKE."""
    return {
        "number": ISSUE,
        "title": "fail-closed smoke-execution gate",
        "state": "OPEN",
        "labels": [{"name": "atdd-issue"}, {"name": "atdd:SMOKE"}],
        "body": "",
    }


@pytest.fixture
def worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated worktree whose Control Root is itself, holding an OBLIGATED item.

    ``ATDD_CONTROL_ROOT`` pins the store inside ``tmp_path`` so no test here can
    read — or write — the developer's real store. The work item and its GitHub
    ``external_ref`` are seeded because that projection is how the gate turns the
    issue number it is handed into the uid the attestation is keyed by; without
    it the check has nothing to look up and (correctly) fails closed, which would
    make injection 2 pass for the wrong reason.

    The ``plan/`` scope and the ``data`` bag binding the work item to it are
    seeded for the mirror-image reason: with no declared live_smoke acceptance the
    opt-in check answers *not applicable* and passes, so injections 1 and 3 would
    go green having never reached the fail-closed logic they exist to pin.
    """
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    data = write_live_smoke_plan_scope(tmp_path)
    with open_state_store(control_root=tmp_path) as store:
        store.objects.upsert(UID, "work_item", state="SMOKE", data=data)
        store.external_refs.link(UID, "github", "issue", str(ISSUE))
    return tmp_path


@pytest.fixture
def clean_registry():
    """Isolate SMOKE->REFACTOR so only the check under test can vote."""
    before = GATE_REGISTRY.checks_for("SMOKE", "REFACTOR")
    GATE_REGISTRY.clear("SMOKE", "REFACTOR")
    yield GATE_REGISTRY
    GATE_REGISTRY.clear("SMOKE", "REFACTOR")
    for chk in before:
        GATE_REGISTRY.register("SMOKE", "REFACTOR", chk)


def _attest(worktree: Path, **overrides) -> None:
    """Record one smoke run through the real producer API.

    ``commit_sha`` is left unset: ``tmp_path`` is not a git checkout, so the
    check resolves no HEAD and the staleness clause stands down. Staleness is
    proven where it can be proven honestly — against a real repository, in the
    end-to-end test.
    """
    run = dict(nodeid="tests/smoke/test_live.py::test_end_to_end",
               outcome="passed", duration_s=4.2, execution_kind="live_smoke")
    run.update(overrides)
    with open_state_store(control_root=worktree) as store:
        record_smoke_execution(store, UID, SmokeRun(**run))


def _attempt_transition(worktree: Path, issue: dict) -> tuple[int, MagicMock]:
    """Drive the real SMOKE->REFACTOR transition; return (rc, update spy)."""
    lifecycle = IssueLifecycle(target_dir=worktree)
    update_spy = MagicMock(return_value=0)
    with patch.object(IssueLifecycle, "_fetch_issue", return_value=issue), \
         patch.object(IssueLifecycle, "_load_config", return_value=GATED_CONFIG), \
         patch.object(IssueLifecycle, "_compliance_gate", return_value=0), \
         patch.object(IssueLifecycle, "_reenter_display_only", return_value=0), \
         patch("atdd.coach.commands.issue.IssueManager.update", update_spy):
        rc = lifecycle.transition(ISSUE, "REFACTOR", force=False)
    return rc, update_spy


# --------------------------------------------------------------------------- #
# Fault injection 1 — no attestation => BLOCKED (the bug being closed)         #
# --------------------------------------------------------------------------- #


def test_no_attestation_blocks_smoke_to_refactor(worktree: Path, smoke_issue, clean_registry):
    """Smoke never ran (no attestation) => SMOKE->REFACTOR must not occur."""
    register_smoke_execution_check(clean_registry)

    rc, update_spy = _attempt_transition(worktree, smoke_issue)

    assert rc != 0, "a missing smoke-execution attestation must return non-zero"
    assert not update_spy.called, (
        "SMOKE->REFACTOR occurred with no proof that smoke ever executed — "
        "IssueManager.update() (the label/phase swap) must never be reached"
    )


# --------------------------------------------------------------------------- #
# Fault injection 2 — attestation present => PROCEEDS (the negative control)   #
# --------------------------------------------------------------------------- #


def test_passing_attestation_allows_smoke_to_refactor(
    worktree: Path, smoke_issue, clean_registry, monkeypatch
):
    """Smoke ran and passed => the gate must let the transition through.

    Without this control the suite could not tell a working gate from one that
    blocks unconditionally.

    #1619: the chokepoint now registers the production checks itself instead of
    consulting only what a caller registered, and ``SMOKE->REFACTOR`` is one of
    ``registrations._CANDIDATE_TRANSITIONS`` — so the real
    ``ApprovalTokenGateCheck`` is on this edge too and fails closed with no token.
    The negative control still has to be a control, so the fixture mints a real
    operator token for the throwaway issue under ``worktree``. The subject of this
    test is unchanged: with the attestation present the transition proceeds, and
    the fault-injection case above still proves the smoke check is what blocks
    when it is absent.
    """
    monkeypatch.setenv("ATDD_APPROVAL_SIGNING_KEY", "spike-1602-negative-control-key")
    assert run_approve(
        [str(ISSUE), "--transition", "SMOKE->REFACTOR", "--by", "operator"],
        target_dir=worktree,
    ) == 0, "fixture precondition: the real approve command must mint the token"

    register_smoke_execution_check(clean_registry)
    _attest(worktree)

    rc, update_spy = _attempt_transition(worktree, smoke_issue)

    assert rc == 0, "a passing smoke-execution attestation must not block the transition"
    assert update_spy.called, (
        "the gate blocked SMOKE->REFACTOR despite a passing smoke attestation — "
        "a gate that blocks everything proves nothing"
    )


# --------------------------------------------------------------------------- #
# Fault injection 3 — check raises => BLOCKED (fail-closed inheritance)        #
# --------------------------------------------------------------------------- #


def test_raising_check_blocks_rather_than_allows(worktree: Path, smoke_issue, clean_registry):
    """An exploding check must FAIL the transition, not wave it through.

    Proves the claim that fail-closed is inherited free from
    ``decision.run_checks`` — the check itself catches nothing here. The
    attestation is present and valid, so a fail-OPEN aggregator would be
    indistinguishable from injection 2; only the raise can make this block.
    """
    register_smoke_execution_check(clean_registry)
    _attest(worktree)

    boom = MagicMock(side_effect=RuntimeError("attestation store unreachable"))
    with patch.object(SmokeExecutionGateCheck, "run", boom):
        rc, update_spy = _attempt_transition(worktree, smoke_issue)

    assert boom.called, "the injected raise never ran — the check was not consulted"
    assert rc != 0, "an errored gate check must fail closed (non-zero), not pass silently"
    assert not update_spy.called, (
        "SMOKE->REFACTOR occurred while the gate check was erroring — "
        "fail-closed inheritance from run_checks is broken"
    )


# --------------------------------------------------------------------------- #
# Supporting proofs — the discriminating read, and the registration seam       #
# --------------------------------------------------------------------------- #


def _verdict(worktree: Path):
    from atdd.coach.gate.decision import GateContext

    ctx = GateContext(issue_number=ISSUE, from_phase="SMOKE",
                      to_phase="REFACTOR", worktree=worktree)
    return SmokeExecutionGateCheck().run(ctx)


@pytest.mark.parametrize(
    "runs, why",
    [
        ([], "an attestation recording no runs"),
        ([{"outcome": "skipped"}], "an all-skipped run (#1076 class: 'passed' by skipping)"),
        ([{"outcome": "failed"}], "a failing run"),
        ([{"duration_s": 0.0}], "a passing run that measured no time (#1192 class)"),
        ([{"outcome": "skipped"}, {"outcome": "failed"}], "several runs, none passing"),
    ],
)
def test_degenerate_attestations_do_not_satisfy_the_gate(worktree: Path, runs, why):
    """The read must discriminate — mere presence of a record is not evidence."""
    for overrides in runs:
        _attest(worktree, **overrides)

    assert not _verdict(worktree).passed, f"{why} must not satisfy the smoke-execution gate"


def test_unknown_work_item_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An issue the store has never heard of blocks; it does not sail through."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))

    result = _verdict(tmp_path)

    assert not result.passed
    assert "no work item" in result.message


def test_operator_typed_stamp_is_not_accepted_as_execution_evidence(worktree: Path):
    """The #358 presentation-ratchet stamp must not satisfy this gate.

    ``.atdd/smoke-evidence/<N>.yaml`` is producible by hand with
    ``atdd validate coder --smoke-required`` without running a test. If reading
    it satisfied this gate, the whole issue would have re-imported the bug.
    """
    stamp = worktree / ".atdd" / "smoke-evidence" / f"{ISSUE}.yaml"
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text(
        f"issue: {ISSUE}\n"
        "note: recorded via `atdd validate coder --smoke-required`\n"
        "recorded_by: alecfokapu\n"
    )

    assert not _verdict(worktree).passed, (
        "an operator-typed stamp satisfied the smoke-EXECUTION gate — "
        "that is the exact bug class this gate exists to close"
    )


def test_another_issues_smoke_run_does_not_satisfy_this_one(worktree: Path):
    """Attestations are per work item; borrowing another's is not evidence."""
    with open_state_store(control_root=worktree) as store:
        store.objects.upsert("some-other-issue", "work_item", state="SMOKE")
        record_smoke_execution(store, "some-other-issue", SmokeRun(
            nodeid="x::y", outcome="passed", duration_s=9.9, execution_kind="live_smoke",
        ))

    assert not _verdict(worktree).passed


def test_registration_is_idempotent_and_targets_smoke_to_refactor(clean_registry):
    """The registration seam: one check, on SMOKE->REFACTOR, however often called."""
    register_smoke_execution_check(clean_registry)
    register_smoke_execution_check(clean_registry)

    checks = clean_registry.checks_for("SMOKE", "REFACTOR")
    assert [c.gate_id for c in checks].count(GATE_ID) == 1, (
        "register_smoke_execution_check must be idempotent"
    )
    assert not any(
        getattr(c, "gate_id", None) == GATE_ID
        for c in clean_registry.checks_for("GREEN", "SMOKE")
    ), "the smoke-execution check must not leak onto other transitions"
