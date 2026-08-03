# URN: test:govern-lifecycle:phase-aware-validator-binding:E057-INTEGRATION-001-forward-pass-exempts-pre-red-owner
# Acceptance: acc:govern-lifecycle:E057-UNIT-001-phase-order-marks-init-planned-pre-test
# Acceptance: acc:govern-lifecycle:E057-INTEGRATION-001-forward-pass-exempts-pre-red-owner
# Acceptance: acc:govern-lifecycle:E057-INTEGRATION-002-forward-pass-still-fires-for-red-plus-owner
# Acceptance: acc:govern-lifecycle:E057-INTEGRATION-003-reverse-pass-orphan-detection-unchanged
# Acceptance: acc:govern-lifecycle:E057-SMOKE-001-real-tester-suite-runs-phase-aware-binding-green
# WMBT: wmbt:govern-lifecycle:E057
# Phase: GREEN
# Layer: application
# Runtime: python

"""Anchored coverage for ``wmbt:govern-lifecycle:E057`` (issue #1242).

Proves the *forward pass* of
``test_repo_validator_binding.collect_violations`` is phase-aware:

  - UNIT-001: ``is_pre_test_phase`` ranks INIT/PLANNED as pre-test (strictly
    before RED in ``phase_machine`` order) and everything else — including
    unknown/BLOCKED/OBSOLETE/None — as not-pre-test (fail-closed).
  - INTEGRATION-001: a harness acceptance with no anchored test is EXEMPT when
    every ``.atdd/manifest.yaml`` session for its wagon is at INIT/PLANNED.
  - INTEGRATION-002: the same acceptance STILL fires when the owning wagon has
    a RED+ session (invariant not weakened) or when no manifest maps the wagon
    (fail-closed).
  - INTEGRATION-003: the reverse (orphan-test) pass is unchanged — it fires
    regardless of phase/manifest.
  - SMOKE-001: the real repo ``collect_violations`` reports zero violations
    after the refinement (the live plan/ RED+ acceptances still bind).

The phase-aware data is read from the authoritative ``.atdd/manifest.yaml``
``sessions[]`` (the #1168 State Store's import source), not a forked store.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import clear_cache
from atdd.tester.validators._acceptance_walker import (
    is_pre_test_phase,
    owning_issue_phase,
)
from atdd.tester.validators.test_repo_validator_binding import collect_violations


pytestmark = [pytest.mark.platform]

_BINDING_RULE = "tester.acceptance-violation.validator-binding-must-be-bidirectional"


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")
    return path


_WMBT_HEADER = """
    urn: "wmbt:demo-wagon:D001"
    step: "define"
    direction: "minimize"
    dimension: "quantity"
    object_of_control: "thing"
    context_clarifier: "fixture"
    lens: "functional.sustainability"
    statement: "minimize thing"
    acceptances:
"""

_HARNESS_ACC_NO_TEST = """
      - identity:
          urn: "acc:demo-wagon:D001-UNIT-001"
          phase: RED
          purpose: "harness declared, test not yet authored"
        harness: { type: unit }
"""


def _write_acceptance(repo_root: Path) -> None:
    """A demo-wagon acceptance declaring harness.type with no anchored test."""
    _write(repo_root / "plan" / "demo-wagon" / "D001.yaml", _WMBT_HEADER + _HARNESS_ACC_NO_TEST)


def _seed_owner(repo_root: Path, *, wagon: str, status: str) -> None:
    """Seed the State Store with a demo work item mapping *wagon* at *status*.

    #1270 slice E migrated ``owning_issue_phase`` to read the store
    (``WorkItemReader``), and slice G deletes ``.atdd/manifest.yaml`` — so the
    owner phase must be seeded into the store, not the (removed) manifest mirror.
    """
    atdd = repo_root / ".atdd"
    atdd.mkdir(exist_ok=True)
    (atdd / "config.yaml").write_text("github:\n  repo: afokapu/atdd\n", encoding="utf-8")

    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=repo_root))
    try:
        create_work_item(
            conn,
            "demo-session",
            state=status,
            data={
                "status": status,
                "wagon": wagon,
                "feature": f"feature:{wagon}:demo",
                "train": "0001-self-compliance-validate",
            },
            github_number=9001,
        )
        conn.commit()
    finally:
        conn.close()


def _binding_violations(repo_root: Path):
    return [v for v in collect_violations(repo_root) if v.rule_id == _BINDING_RULE]


# ---------------------------------------------------------------------------
# UNIT-001 — phase-order comparison
# ---------------------------------------------------------------------------
def test_unit_001_phase_order_marks_init_planned_pre_test():
    # acc:govern-lifecycle:E057-UNIT-001-phase-order-marks-init-planned-pre-test
    assert is_pre_test_phase("INIT") is True
    assert is_pre_test_phase("PLANNED") is True
    for due in ("RED", "GREEN", "SMOKE", "REFACTOR", "COMPLETE"):
        assert is_pre_test_phase(due) is False, due
    for nonlinear in ("BLOCKED", "OBSOLETE", "SHIPPED", "", None):
        assert is_pre_test_phase(nonlinear) is False, nonlinear


# ---------------------------------------------------------------------------
# INTEGRATION-001 — forward pass exempts a pre-RED owner
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["INIT", "PLANNED"])
def test_integration_001_forward_pass_exempts_pre_red_owner(tmp_path: Path, status: str):
    # acc:govern-lifecycle:E057-INTEGRATION-001-forward-pass-exempts-pre-red-owner
    _write_acceptance(tmp_path)
    _seed_owner(tmp_path, wagon="demo-wagon", status=status)

    assert _binding_violations(tmp_path) == []


# ---------------------------------------------------------------------------
# INTEGRATION-002 — forward pass still fires for RED+ owner / fail-closed
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status", ["RED", "GREEN", "REFACTOR", "COMPLETE"])
def test_integration_002_forward_pass_fires_for_red_plus_owner(tmp_path: Path, status: str):
    # acc:govern-lifecycle:E057-INTEGRATION-002-forward-pass-still-fires-for-red-plus-owner
    _write_acceptance(tmp_path)
    _seed_owner(tmp_path, wagon="demo-wagon", status=status)

    vs = _binding_violations(tmp_path)
    assert len(vs) == 1
    assert "acc:demo-wagon:D001-UNIT-001" in vs[0].detail


def test_integration_002_forward_pass_fail_closed_without_manifest(tmp_path: Path):
    # acc:govern-lifecycle:E057-INTEGRATION-002-forward-pass-still-fires-for-red-plus-owner
    # No .atdd/manifest.yaml at all → wagon unmapped → fail-closed → require the test.
    _write_acceptance(tmp_path)

    vs = _binding_violations(tmp_path)
    assert len(vs) == 1
    assert "acc:demo-wagon:D001-UNIT-001" in vs[0].detail


def test_integration_002_fail_closed_when_wagon_unmapped(tmp_path: Path):
    # acc:govern-lifecycle:E057-INTEGRATION-002-forward-pass-still-fires-for-red-plus-owner
    # Manifest exists but maps a DIFFERENT wagon → no session for demo-wagon → require.
    _write_acceptance(tmp_path)
    _seed_owner(tmp_path, wagon="other-wagon", status="PLANNED")

    vs = _binding_violations(tmp_path)
    assert len(vs) == 1


# ---------------------------------------------------------------------------
# INTEGRATION-003 — reverse pass unchanged
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("with_planned_manifest", [False, True])
def test_integration_003_reverse_pass_orphan_detection_unchanged(
    tmp_path: Path, with_planned_manifest: bool
):
    # acc:govern-lifecycle:E057-INTEGRATION-003-reverse-pass-orphan-detection-unchanged
    (tmp_path / "plan").mkdir()
    orphan_urn = "acc:demo-wagon:Z999-UNIT-001"
    _write(
        tmp_path / "python" / "demo_wagon" / "tests" / "test_orphan.py",
        f"""
        # URN: test:demo-wagon:orphan
        # Acceptance: {orphan_urn}
        # WMBT: wmbt:demo-wagon:Z999
        # Phase: GREEN
        # Layer: domain

        def test_orphan():
            pass
        """,
    )
    if with_planned_manifest:
        _seed_owner(tmp_path, wagon="demo-wagon", status="PLANNED")

    vs = _binding_violations(tmp_path)
    assert any(orphan_urn in v.detail for v in vs), (
        "reverse-pass orphan detection must fire regardless of phase/manifest"
    )


# ---------------------------------------------------------------------------
# Owning-issue-phase mapping (supports INTEGRATION-001/002)
# ---------------------------------------------------------------------------
def test_owning_issue_phase_returns_most_advanced_for_wagon(tmp_path: Path):
    # acc:govern-lifecycle:E057-INTEGRATION-002-forward-pass-still-fires-for-red-plus-owner
    from atdd.tester.validators._acceptance_walker import iter_repo_acceptances

    _write_acceptance(tmp_path)
    # Two owning work items for the wagon (store — #1270 slice E/G): PLANNED + RED.
    atdd = tmp_path / ".atdd"
    atdd.mkdir(exist_ok=True)
    (atdd / "config.yaml").write_text("github:\n  repo: afokapu/atdd\n", encoding="utf-8")
    from atdd.state.db import connect, init_state_store
    from atdd.state.work_item_writer import create_work_item

    conn = connect(init_state_store(start=tmp_path))
    try:
        for slug, status, num in (("a", "PLANNED", 1), ("b", "RED", 2)):
            create_work_item(
                conn, slug, state=status,
                data={"status": status, "wagon": "demo-wagon"},
                github_number=num,
            )
        conn.commit()
    finally:
        conn.close()
    acc = next(iter_repo_acceptances(tmp_path))
    # Most-advanced phase among the wagon's sessions wins → RED (not exempt).
    assert owning_issue_phase(tmp_path, acc) == "RED"
    assert is_pre_test_phase(owning_issue_phase(tmp_path, acc)) is False


def test_owning_issue_phase_none_when_unmapped(tmp_path: Path):
    # acc:govern-lifecycle:E057-INTEGRATION-002-forward-pass-still-fires-for-red-plus-owner
    from atdd.tester.validators._acceptance_walker import iter_repo_acceptances

    _write_acceptance(tmp_path)  # no manifest
    acc = next(iter_repo_acceptances(tmp_path))
    assert owning_issue_phase(tmp_path, acc) is None


# ---------------------------------------------------------------------------
# SMOKE-001 — real repo still reports zero binding violations
# ---------------------------------------------------------------------------
def test_smoke_001_real_repo_binding_clean_after_refinement():
    # acc:govern-lifecycle:E057-SMOKE-001-real-tester-suite-runs-phase-aware-binding-green
    repo_root = find_repo_root()
    vs = [v for v in collect_violations(repo_root) if v.rule_id == _BINDING_RULE]
    assert vs == [], (
        "phase-aware refinement must not introduce binding violations on the live repo; "
        f"got {[ (v.location, v.detail[:60]) for v in vs ]}"
    )
