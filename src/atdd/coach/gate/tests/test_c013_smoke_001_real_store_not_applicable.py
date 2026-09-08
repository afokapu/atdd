# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C013-SMOKE-001-real-store-not-applicable-yields-the-new-verdict
# Acceptance: acc:govern-lifecycle:C013-SMOKE-001-real-store-not-applicable-yields-the-new-verdict
# WMBT: wmbt:govern-lifecycle:C013
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C013-SMOKE-001 — the migrated branch, against a real State Store.

``SmokeExecutionGateCheck._not_applicable`` is the one place in the tree that had
already hit this defect and worked around it. Its docstring separates that branch
from the fail-closed body *"so the two answers cannot be confused while reading"*
— an accurate description of a distinction the return type could not carry, since
both answers had to be spelled ``passed=True``. This file is the proof it now
carries one.

**And the proof that nothing else moved.** ``.atdd/config.yaml`` sets
``SMOKE->REFACTOR: true`` and ``registrations.py`` registers this check for that
edge, so ``_not_applicable`` is on the live enforcement path. Nearly every work
item in the repo reaches it. If the migrated verdict blocked, that edge would
become reachable only through ``--force`` for essentially the whole repo — the
rubber-stamp failure ``smoke_obligation`` was built to prevent. So the verdict
changes and the decision does not, and both halves are asserted here.

Real store, real migration, real check, real obligation resolver, under an
isolated Control Root. Nothing is monkeypatched and no record is hand-placed:
the attestation in the negative-control case is written through the real producer
API, the way a real pytest run writes one.

RED state: ``atdd.coach.gate.decision`` declares no ``GateVerdict``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from atdd.coach.gate.decision import GateContext, GateVerdict, evaluate_gate
from atdd.coach.gate.live_smoke import write_live_smoke_plan_scope
from atdd.coach.gate.smoke_execution_check import SmokeExecutionGateCheck
from atdd.state.smoke_evidence import open_state_store

pytestmark = [pytest.mark.platform]

#: An issue bound to nothing, standing in for the ~780 work items in this repo
#: that declare no plan scope and must not notice this migration happened.
ISSUE = 1719
UID = "gate-check-could-not-check-verdict"

#: An issue that DID promise a live-smoke run — the negative control, without
#: which "not applicable everywhere" would satisfy this file for the wrong reason.
OBLIGATED_ISSUE = 1602
OBLIGATED_UID = "smoke-execution-gate-wiring"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An isolated worktree whose Control Root is itself.

    ``ATDD_CONTROL_ROOT`` pins every store read and write inside ``tmp_path``, so
    nothing here can consult — or disturb — the developer's real store.
    """
    monkeypatch.setenv("ATDD_CONTROL_ROOT", str(tmp_path))
    return tmp_path


def _register(repo: Path, uid: str, issue: int, data: Optional[dict] = None) -> None:
    """Seed a work item in SMOKE and the GitHub ref the gate resolves it by."""
    with open_state_store(control_root=repo) as store:
        store.objects.upsert(uid, "work_item", state="SMOKE", data=data or {})
        store.external_refs.link(uid, "github", "issue", str(issue))


def _verdict(repo: Path, issue: int):
    """The real SMOKE->REFACTOR result for *issue* in *repo*."""
    return SmokeExecutionGateCheck().run(
        GateContext(issue_number=issue, from_phase="SMOKE", to_phase="REFACTOR", worktree=repo)
    )


# --------------------------------------------------------------------------- #
# The migration: the branch now carries a verdict instead of a bare bool       #
# --------------------------------------------------------------------------- #
def test_an_issue_owing_no_live_smoke_run_yields_not_applicable(repo: Path) -> None:
    """The answer the docstring already distinguished, now in the type."""
    _register(repo, UID, ISSUE)

    result = _verdict(repo, ISSUE)

    assert result.verdict is GateVerdict.NOT_APPLICABLE, (
        f"the not-applicable branch still reports {result.verdict}; it is the one "
        f"in-tree instance this vocabulary exists to give a home to"
    )
    assert result.verdict is not GateVerdict.PASS, (
        "'this issue owes nothing' was reported as 'the obligation was met'"
    )
    assert "not applicable" in result.message


def test_the_transition_outcome_for_that_issue_is_unchanged(repo: Path) -> None:
    """The guarantee that makes this a vocabulary correction, not a policy change.

    SMOKE->REFACTOR is live-gated in this repo. A blocking migration here strands
    every issue that declares no live_smoke acceptance behind ``--force``.
    """
    _register(repo, UID, ISSUE)

    outcome = evaluate_gate([_verdict(repo, ISSUE)])

    assert outcome.proceed is True, (
        "migrating _not_applicable changed the decision for an issue that owes the "
        "gate nothing — SMOKE->REFACTOR is enabled in .atdd/config.yaml, so this "
        "would strand nearly every work item in the repo behind --force"
    )
    assert outcome.failures == ()
    assert outcome.unobservable == ()


def test_the_legacy_bool_still_reads_true_for_callers_that_read_it(repo: Path) -> None:
    """``passed`` survives the migration, so no existing reader is disturbed."""
    _register(repo, UID, ISSUE)

    assert _verdict(repo, ISSUE).passed is True


# --------------------------------------------------------------------------- #
# The negative control: the teeth were not filed off on the way through        #
# --------------------------------------------------------------------------- #
def test_an_obligated_issue_with_no_attestation_still_fails(repo: Path) -> None:
    """Declared and not discharged is still FAIL, and still blocks.

    Without this, a check that returned NOT_APPLICABLE unconditionally would pass
    every other case in this file.
    """
    _register(repo, OBLIGATED_UID, OBLIGATED_ISSUE, write_live_smoke_plan_scope(repo))

    result = _verdict(repo, OBLIGATED_ISSUE)

    assert result.verdict is GateVerdict.FAIL, (
        f"an issue that declared a live_smoke acceptance and produced no attestation "
        f"reported {result.verdict}; the fail-closed path must stay a failure"
    )
    assert evaluate_gate([result]).proceed is False
