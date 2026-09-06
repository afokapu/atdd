# URN: test:govern-lifecycle:enforcing-phase-transition-gate:C014-UNIT-001-the-classifier-sees-this-repos-own-code
# Acceptance: acc:govern-lifecycle:C014-UNIT-001-the-classifier-sees-this-repos-own-code
# WMBT: wmbt:govern-lifecycle:C014
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C014-UNIT-001 — the PR phase-alignment classifier can see this repo's own code.

``_CODE_PATH_PREFIXES`` lists ``python/``, ``web/src/``, ``supabase/functions/``,
``packages/`` and ``supabase/migrations/`` — the layout of the downstream consumer
repo named in the validator's own module docstring (its PRs #307, #308). This
toolkit's code lives under ``src/atdd/``, which matches none of them, so
``_classify_changed_files`` files every source file under ``other`` and
``evaluate_phase_violations`` returns early on ``if not classified.get("code")``.

Measured 2026-08-03 through the live ``PRManager`` across all 18 open PRs and 196
changed files: ``code=0`` on every single PR, with 46 ``src/`` files sitting in
``other``. So neither ``SPEC-COACH-PRGATE-0002`` (INIT/PLANNED warn) nor
``COACH-PRGATE-0003`` (GREEN fail, severity 4) has ever fired in this repo. The
validator is bound, wired, dispositioned and blind — which is worse than absent,
because it produces a pass.

These assertions are deliberately kept off the live GitHub API: the module-level
``pytestmark`` on the validator marks its own inline unit tests ``platform`` and
``github_api``, so they are deselected by the very marker expression C014's other
half is about. This file carries no markers, so it runs wherever the suite runs.
"""
from __future__ import annotations

from atdd.coach.validators._violation import Violation
from atdd.coach.validators.test_pr_phase_alignment import (
    RULE_ID_PRGATE_GREEN,
    SEVERITY_PRGATE_GREEN,
    _classify_changed_files,
    evaluate_phase_violations,
    select_blocking_violations,
)

# Real paths from this repo's own tree. `src/atdd/coach/commands/issue.py` is the
# single code file on PR#1589, whose issue #1583 sits at GREEN — the live
# COACH-PRGATE-0003 case this fix surfaces.
_OWN_CODE = "src/atdd/coach/commands/issue.py"
_OWN_MODULE = "src/atdd/coach/utils/repo.py"


# --------------------------------------------------------------------------- #
# Classification                                                               #
# --------------------------------------------------------------------------- #


def test_a_source_file_in_this_repos_own_tree_classifies_as_code():
    """The one line. Today this file lands in ``other`` and the evaluator bails."""
    classified = _classify_changed_files([_OWN_MODULE])

    assert classified["code"] == [_OWN_MODULE]
    assert classified["other"] == []


def test_the_consumer_repo_prefixes_still_classify_as_code():
    """The fix adds a prefix; it must not remove the ones already there."""
    consumer_files = [
        "python/auth/login.py",
        "web/src/match/Match.tsx",
        "supabase/functions/handler.ts",
        "packages/core/index.ts",
        "supabase/migrations/0001_init.sql",
    ]
    classified = _classify_changed_files(consumer_files)

    assert sorted(classified["code"]) == sorted(consumer_files)


def test_a_test_file_in_this_repos_own_tree_still_classifies_as_test():
    """Test patterns are matched BEFORE the code prefixes, and must stay that way.

    Otherwise adding ``src/`` retroactively turns every RED-phase PR in this repo
    into a violation — the opposite of what the rules say, since RED is the phase
    at which test files are the expected content.

    A consequence specific to this repo, worth stating because it bounds what the
    fix reaches: every validator here is a pytest module named ``test_*.py``, so
    ``/test_`` matches and a PR that changes only validators classifies as tests,
    not code, at every phase. That follows from the precedence above rather than
    from the prefix list, so it is not something adding ``src/`` could change.
    """
    test_files = [
        "src/atdd/coach/gate/tests/test_c013_unit_001_could_not_check_blocks.py",
        "src/atdd/coach/validators/test_pr_phase_alignment.py",
    ]
    classified = _classify_changed_files(test_files)

    assert classified["test"] == test_files
    assert classified["code"] == []


def test_plan_and_contract_artifacts_still_classify_as_plan():
    """The artifact-only phases stay quiet — this is a classification fix only."""
    artifacts = [
        "plan/govern_lifecycle/C014.yaml",
        "contracts/commons/error/response.schema.json",
        "telemetry/events.yaml",
        ".atdd/config.yaml",
    ]
    classified = _classify_changed_files(artifacts)

    assert sorted(classified["plan"]) == sorted(artifacts)
    assert classified["code"] == []


# --------------------------------------------------------------------------- #
# The rules become reachable                                                   #
# --------------------------------------------------------------------------- #


def test_green_with_this_repos_own_code_produces_the_structured_violation():
    """COACH-PRGATE-0003, severity 4 — the path #1670 believes is enforcing."""
    classified = _classify_changed_files([_OWN_CODE])
    items = evaluate_phase_violations(
        pr_number=1589,
        issue_number=1583,
        phase="GREEN",
        classified=classified,
    )

    structured = [v for v in items if isinstance(v, Violation)]
    assert len(structured) == 1
    assert structured[0].rule_id == RULE_ID_PRGATE_GREEN
    assert structured[0].severity == SEVERITY_PRGATE_GREEN


def test_init_and_planned_with_this_repos_own_code_produce_a_violation():
    """SPEC-COACH-PRGATE-0002 — reachable, and a structured rule since #1791."""
    classified = _classify_changed_files([_OWN_CODE])

    for phase in ("INIT", "PLANNED"):
        items = evaluate_phase_violations(
            pr_number=1660,
            issue_number=1653,
            phase=phase,
            classified=classified,
        )
        assert any(isinstance(item, Violation) for item in items), phase
        assert items[0].rule_id == "COACH-PRGATE-0002", phase


def test_init_with_plan_only_changes_stays_quiet():
    """INIT is exactly the phase for plan artifacts — they must not trip the gate."""
    classified = _classify_changed_files(["plan/govern_lifecycle/E070.yaml"])
    assert evaluate_phase_violations(
        pr_number=1660, issue_number=1653, phase="INIT", classified=classified,
    ) == []


def test_early_phase_gate_routes_through_the_shared_pr_scoper():
    """#1791 wiring: this gate narrows to the PR under validation like its siblings.

    The selector's own behaviour is E070's to prove (unit_002/unit_003); this
    asserts only that COACH-PRGATE-0002 is routed through it rather than
    failing every branch for a sibling PR's offense.
    """
    offenders = [
        Violation(rule_id="COACH-PRGATE-0002", severity=4,
                  location=f"PR#{n}:0", detail=f"PR #{n} ships code at INIT")
        for n in (1763, 1764)
    ]
    assert select_blocking_violations(offenders, current_pr=1793) == []
    assert [v.location for v in select_blocking_violations(offenders, 1764)] == ["PR#1764:0"]


# --------------------------------------------------------------------------- #
# The quiet cases stay quiet                                                   #
# --------------------------------------------------------------------------- #


def test_green_with_only_this_repos_own_tests_stays_quiet():
    classified = _classify_changed_files(
        ["src/atdd/coach/gate/tests/test_c013_unit_001_could_not_check_blocks.py"]
    )
    assert evaluate_phase_violations(
        pr_number=1, issue_number=2, phase="GREEN", classified=classified
    ) == []


def test_post_smoke_phases_with_this_repos_own_code_stay_quiet():
    classified = _classify_changed_files([_OWN_CODE])
    for phase in ("SMOKE", "REFACTOR", "COMPLETE"):
        assert evaluate_phase_violations(
            pr_number=1, issue_number=2, phase=phase, classified=classified
        ) == [], phase


def test_an_unresolved_phase_stays_quiet():
    classified = _classify_changed_files([_OWN_CODE])
    assert evaluate_phase_violations(
        pr_number=1, issue_number=2, phase=None, classified=classified
    ) == []
