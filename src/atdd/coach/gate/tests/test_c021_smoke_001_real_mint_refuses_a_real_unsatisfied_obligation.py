# URN: test:govern-lifecycle:operator-approval-token-gate:C021-SMOKE-001-real-mint-refuses-a-real-unsatisfied-obligation
# Acceptance: acc:govern-lifecycle:C021-SMOKE-001-real-mint-refuses-a-real-unsatisfied-obligation
# WMBT: wmbt:govern-lifecycle:C021
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C021-SMOKE-001 — the real mint, the real registrars, a real State Store.

The invocation under test is the one that actually produced the defect. Measured
2026-08-03 on ``#1726``: ``PLANNED``, ``RED``, ``GREEN``, ``SMOKE`` and
``REFACTOR`` were all REFUSED by the template-compliance gate while both of its
``atdd coach approve`` calls SUCCEEDED, leaving ``PLANNED-RED.json`` and
``SMOKE-REFACTOR.json`` on the shared Control Root for an issue that never left
``INIT``. Correctly attributed, cryptographically sound, meaningless.

Nothing on the mint or the gate path is mocked, stubbed or monkeypatched: the
real ``approve_command.run``, the real ``register_approval_checks`` and
``register_smoke_execution_check``, the real ``SmokeExecutionGateCheck``, a real
migrated SQLite State Store and a real git checkout. Only the Control Root is
synthetic — ``tmp_path`` with throwaway uids and issue numbers — so no live
issue, no live Control Root and no GitHub I/O is touched.

BOTH LEGS ARE LOAD-BEARING. The obligated leg proves the mint refuses. The
owing-nothing leg proves it still mints, and is what stops "refuses everything"
from satisfying this file — which would strand the repo at SMOKE just as surely
as the vacuous token failed to gate it.

RED state: ``atdd.coach.gate.mint_gate`` does not exist.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.gate.approval_paths import approval_token_path
from atdd.coach.gate.approve_command import run as approve
from atdd.coach.gate.live_smoke import write_live_smoke_plan_scope
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform]

#: Owes a live-smoke run and has produced no attestation — the mint must refuse.
OBLIGATED_ISSUE = 999601
OBLIGATED_UID = "c021-obligated-work-item"

#: Owes nothing, the shape of 787 of 787 work items when the edge was enabled.
UNOBLIGATED_ISSUE = 999602
UNOBLIGATED_UID = "c021-unobligated-work-item"

#: Owes a live-smoke run like ``OBLIGATED_ISSUE``, but is STANDING AT PLANNED —
#: the scope control at the bottom of this file. It is a third work item rather
#: than a second edge on the obligated one because since #1735 a mint is refused
#: outright for an edge the issue is not standing on, and an issue cannot stand at
#: SMOKE and PLANNED at once.
PLANNED_ISSUE = 999603
PLANNED_UID = "c021-planned-obligated-work-item"


#: Every edge the registrars touch, so the fixture below can put the shared
#: registry back exactly as it found it.
_CANDIDATE_EDGES = (
    ("PLANNED", "RED"), ("RED", "GREEN"), ("GREEN", "SMOKE"),
    ("SMOKE", "REFACTOR"), ("REFACTOR", "COMPLETE"),
)


@pytest.fixture(autouse=True)
def restore_the_shared_registry():
    """Put ``GATE_REGISTRY`` back after each test.

    This file drives the REAL mint, which registers into the REAL module-level
    registry — that is the behaviour under test (#1619: the registrars run at
    exactly one call site, so the mint has to call them itself). But
    ``registrations.py`` is explicitly non-side-effecting on import precisely
    because a populated ``GATE_REGISTRY`` breaks #1020's migration-safety tests,
    which assert against the live registry that collection imports every module
    into. Leaving it populated made
    ``test_e050_integration_002_token_allows_transition`` and
    ``test_e045_integration_failing_check_refuses_transition`` fail when run after
    this file and pass in isolation — an order-dependent false red manufactured by
    the very test asserting the registrars run.

    Snapshot and restore through the public API, so fidelity is not traded away:
    the registrars, the checks and the registry class are all the real ones.
    """
    from atdd.coach.gate.registry import GATE_REGISTRY

    before = {edge: GATE_REGISTRY.checks_for(*edge) for edge in _CANDIDATE_EDGES}
    yield
    for edge, checks in before.items():
        GATE_REGISTRY.clear(*edge)
        for check in checks:
            GATE_REGISTRY.register(*edge, check)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real git checkout whose Control Root is itself, gating SMOKE->REFACTOR."""
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "gate:\n  transitions:\n    PLANNED->RED: true\n    SMOKE->REFACTOR: true\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit",
         "-q", "--allow-empty", "-m", "root"],
        cwd=tmp_path, check=True,
    )
    return tmp_path


#: The branch binding #1721 requires of every mint. Seeded on every work item
#: here because this file drives the REAL command: without it the mint refuses on
#: the missing binding before it ever reaches the gate run, and every refusal
#: assertion below would pass for #1721's reason instead of this acceptance's.
#: Real state rather than a bypass, per the pattern #1721 set in C012-UNIT-001.
_BRANCH = "feat/token-proves-gates-passed"


def _register(
    repo: Path, uid: str, issue: int, data: dict | None = None, state: str = "SMOKE"
) -> None:
    """Seed one work item. ``state`` defaults to SMOKE — the edge under test.

    It is a parameter at all because of #1735: the mint now refuses for an edge the
    issue is not standing on, so the PLANNED->RED control below needs a work item
    recorded at PLANNED rather than the SMOKE one it used to reuse.
    """
    with open_state_store(control_root=repo) as store:
        store.objects.upsert(
            uid, "work_item", state=state, data={**(data or {}), "branch": _BRANCH}
        )
        store.external_refs.link(uid, "github", "issue", str(issue))


def _mint(repo: Path, issue: int, transition: str) -> int:
    """The real command, with an empty env so no ambient agent session leaks in."""
    return approve([str(issue), "--transition", transition], target_dir=repo, env={})


def _tokens(repo: Path) -> list[Path]:
    return list(repo.rglob("SMOKE-REFACTOR.json"))


# --------------------------------------------------------------------------- #
# The refusal — a declared obligation with nothing discharging it              #
# --------------------------------------------------------------------------- #
def test_an_unsatisfied_obligation_refuses_the_mint(repo: Path) -> None:
    """The central claim of #1670 slice C, through the command that carries it."""
    _register(repo, OBLIGATED_UID, OBLIGATED_ISSUE, write_live_smoke_plan_scope(repo))

    assert _mint(repo, OBLIGATED_ISSUE, "SMOKE->REFACTOR") != 0, (
        "the mint signed an approval for an issue that promised a live-smoke run "
        "and produced no attestation — exactly the receipt #1726 collected twice"
    )


def test_the_refused_mint_leaves_no_token_anywhere_under_the_control_root(repo: Path) -> None:
    """``ApprovalTokenGateCheck`` reads the filesystem, so this is the real assertion.

    A refusal that printed an error and wrote the file would have changed nothing
    about what the enforcing gate later accepts.
    """
    _register(repo, OBLIGATED_UID, OBLIGATED_ISSUE, write_live_smoke_plan_scope(repo))

    _mint(repo, OBLIGATED_ISSUE, "SMOKE->REFACTOR")

    assert not approval_token_path(repo, OBLIGATED_ISSUE, "SMOKE", "REFACTOR").exists()
    assert _tokens(repo) == [], (
        "a SMOKE-REFACTOR token exists somewhere under the Control Root after a "
        "refused mint, including the worktree-local path the gate still honours"
    )


def test_the_refusal_names_the_clause_the_smoke_verdict_refused_on(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refusal an operator cannot act on is barely better than the vacuous mint."""
    _register(repo, OBLIGATED_UID, OBLIGATED_ISSUE, write_live_smoke_plan_scope(repo))

    _mint(repo, OBLIGATED_ISSUE, "SMOKE->REFACTOR")
    out = capsys.readouterr().out

    assert "smoke_not_attested" in out, (
        f"the refusal did not name the clause the verdict carried, so the "
        f"operator cannot tell which of four rejection reasons applies:\n{out}"
    )


# --------------------------------------------------------------------------- #
# The control — owing nothing must still mint, or the repo strands at SMOKE    #
# --------------------------------------------------------------------------- #
def test_an_issue_owing_no_live_smoke_still_mints(repo: Path) -> None:
    """787 of 787 work items were this shape when the edge was enabled."""
    _register(repo, UNOBLIGATED_UID, UNOBLIGATED_ISSUE)

    assert _mint(repo, UNOBLIGATED_ISSUE, "SMOKE->REFACTOR") == 0, (
        "the mint refused an issue that owes no live smoke; this strands every "
        "such issue at SMOKE with --force as the only exit"
    )
    assert approval_token_path(repo, UNOBLIGATED_ISSUE, "SMOKE", "REFACTOR").exists()


def test_the_minted_token_satisfies_the_real_enforcing_gate(repo: Path) -> None:
    """The receipt must still be the artifact the gate accepts.

    A conditional mint that wrote something the gate then rejected would have
    replaced a meaningless token with an unusable one.
    """
    from atdd.coach.gate.decision import GateContext, evaluate_transition_gate
    from atdd.coach.gate.registrations import (
        register_approval_checks,
        register_smoke_execution_check,
    )
    from atdd.coach.gate.registry import GateRegistry

    _register(repo, UNOBLIGATED_UID, UNOBLIGATED_ISSUE)
    assert _mint(repo, UNOBLIGATED_ISSUE, "SMOKE->REFACTOR") == 0

    registry = GateRegistry()
    register_approval_checks(registry)
    register_smoke_execution_check(registry)
    outcome = evaluate_transition_gate(
        registry,
        {"gate": {"transitions": {"SMOKE->REFACTOR": True}}},
        GateContext(
            issue_number=UNOBLIGATED_ISSUE, from_phase="SMOKE",
            to_phase="REFACTOR", worktree=repo,
        ),
    )

    assert outcome.proceed is True, (
        f"the token the mint wrote does not satisfy the gate it was minted for: "
        f"{[b.message for b in outcome.blockers]}"
    )


# --------------------------------------------------------------------------- #
# The scope — one edge, and no other                                          #
# --------------------------------------------------------------------------- #
def test_planned_to_red_is_unaffected_in_both_cases(repo: Path) -> None:
    """Slice C is SMOKE->REFACTOR alone.

    On the four other forward edges the registry holds nothing but
    ``ApprovalTokenGateCheck``, so a conditional mint there would consult the
    approval check to decide whether to write an approval. This asserts the
    narrowing is real and not merely intended: an issue carrying the SAME
    unsatisfied live-smoke obligation that gets SMOKE->REFACTOR refused above
    still mints PLANNED->RED.

    It is a THIRD work item, not ``OBLIGATED_ISSUE`` again. This control used to
    mint PLANNED->RED for the issue standing at SMOKE, and #1735 — which refuses
    any mint for an edge the issue is not standing on — now refuses that with "is
    at SMOKE, not PLANNED". #1735's precondition is correct and the control is
    load-bearing (the SMOKE->REFACTOR-only scope is a ruling recorded in #1670),
    so the fixture is what changes: the obligation is reproduced on an issue
    actually standing at PLANNED. ``write_live_smoke_plan_scope`` writes the same
    plan artifacts and returns the same scope binding, so the obligation is
    identical and only the phase differs — which is the one variable this asserts on.
    """
    _register(
        repo, PLANNED_UID, PLANNED_ISSUE,
        write_live_smoke_plan_scope(repo), state="PLANNED",
    )

    assert _mint(repo, PLANNED_ISSUE, "PLANNED->RED") == 0, (
        "the conditional mint leaked onto PLANNED->RED, where the only registered "
        "check is the approval check whose artifact the mint is producing"
    )
    assert approval_token_path(repo, PLANNED_ISSUE, "PLANNED", "RED").exists()
