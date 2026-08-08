# URN: test:govern-lifecycle:bind-issue-train:C018-SMOKE-001-real-validate-coach-reports-the-train-reference
# Acceptance: acc:govern-lifecycle:C018-SMOKE-001-real-validate-coach-reports-the-train-reference
# WMBT: wmbt:govern-lifecycle:C018
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: The real `atdd validate coach --local` selects and RUNS this validator over a real checkout, so the rules are enforced by the shipped gate rather than only by tests that import the scanner.
"""SMOKE test for acc:govern-lifecycle:C018-SMOKE-001-real-validate-coach-reports-the-train-reference.

wagon: govern-lifecycle | feature: bind-issue-train | WMBT: wmbt:govern-lifecycle:C018

A validator the shipped gate never selects enforces nothing, and that is not
hypothetical here: ``atdd validate <phase> --local --skip-api`` selects
``-m "(not github_api) and (not platform)"``, and during #1635's planner pass the
mandated gate reported 211 passed while the full validator directory was red,
because ~207 validators carry the ``platform`` marker. Selection is therefore
asserted, never assumed — and this validator deliberately carries no marker.

Real: a separate real pytest process, over the real coach validator directory, in
a real checkout. No monkeypatching of the validator or its resolver.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_SRC = Path(__file__).resolve().parents[4]
_COACH_VALIDATORS = _SRC / "atdd" / "coach" / "validators"

_VALIDATOR_FILE = _COACH_VALIDATORS / "test_issue_train_binding.py"
_VALIDATOR_ID = "test_issue_train_binding"
_REFERENCE_RULE = "coach.train-reference.resolves-to-registered-train"
_INTERLOCKING_RULE = "coach.train-reference.resolved-train-has-interlocking"


def _pytest(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=_SRC.parent, env=env, capture_output=True, text=True, timeout=600,
    )


def _collect(*extra: str) -> subprocess.CompletedProcess:
    return _pytest(str(_COACH_VALIDATORS), "--collect-only", "-q", *extra)


def test_the_validator_file_ships_in_the_coach_validator_directory() -> None:
    """CI runs `pytest src/atdd/coach/validators/`; the rules must live there."""
    assert _VALIDATOR_FILE.exists(), (
        f"expected the train-binding validator at {_VALIDATOR_FILE}. A rule whose "
        "validator lives outside the CI-collected paths is not enforced by CI at "
        "all (#1643)."
    )


def test_the_real_gate_collects_the_validator() -> None:
    """Discovered and selected the way CI discovers it — not merely importable."""
    result = _collect()

    assert result.returncode == 0, (
        f"collecting the coach validator directory failed:\n{result.stdout}\n{result.stderr}"
    )
    assert _VALIDATOR_ID in result.stdout, (
        "the train-binding validator was not collected by the real gate, so it "
        "enforces nothing regardless of what it asserts"
    )


def test_the_validator_survives_the_gate_marker_expression() -> None:
    """The trap that hid a real failure during #1635's planner pass."""
    result = _collect("-m", "(not github_api) and (not platform)")

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert _VALIDATOR_ID in result.stdout, (
        "the train-binding validator is deselected by the gate's own marker "
        "expression, so `atdd validate coach --local --skip-api` would report "
        "PASS while never running it"
    )


def test_both_rules_resolve_through_the_shipped_registry() -> None:
    """The rules must be registered, not merely referenced by a validator."""
    from atdd.coach.utils.rule_binding import RuleNotInRegistryError, bind_rule

    for rule_id in (_REFERENCE_RULE, _INTERLOCKING_RULE):
        try:
            bind_rule(rule_id)
        except RuleNotInRegistryError as exc:
            pytest.fail(f"rule {rule_id!r} is not in the shipped registry: {exc}")


def test_the_real_run_reports_a_dangling_reference(tmp_path) -> None:
    """It RUNS, against a real store, and says what it found.

    Collection alone is not enforcement: a validator can be collected and then
    scan nothing. This drives the real validator in a separate real process
    against a real on-disk State Store and a real ``plan/`` tree — one issue whose
    train resolves and one whose train does not, which is the repository state
    C018-SMOKE-001 declares.

    THE CORPUS IS BUILT BY THE TEST, NOT INHERITED. The first version of this
    asserted against "this checkout's own" store and passed only on a developer
    machine: CI checks out a tree with no ``.atdd/state/state.sqlite`` (it is
    gitignored), so the scan saw zero rows, reported nothing, and the assertion
    read that as "collected but enforced nothing". Same defect class as the
    ambient-repo fault control in the validator itself — an assertion resting on
    state that happens to exist where it was written.

    Asserted through the ADVISORY warning text rather than through an exit code,
    because the outcome is governed by each node's declared disposition and this
    test must not pin policy the convention owns.
    """
    from .._store_issue_rows import issue_backed_rows  # noqa: F401  (ships check)
    from ._bind_issue_train_helpers import (
        ABSENT_TRAIN, CONSUMER_TRAIN, control_root, open_store, seed_issue,
        write_consumer_plan_tree,
    )

    root = control_root(tmp_path)
    write_consumer_plan_tree(root)
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True, timeout=60)

    store = open_store(root)
    seed_issue(store, slug="resolves", issue_number=940001, train=CONSUMER_TRAIN)
    seed_issue(store, slug="dangles", issue_number=940002, train=ABSENT_TRAIN)
    store.conn.commit()
    store.conn.close()

    env = dict(os.environ)
    env["PYTHONPATH"] = str(_SRC)
    env["ATDD_CONTROL_ROOT"] = str(root)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(_VALIDATOR_FILE),
         "-q", "-p", "no:cacheprovider", "-W", "always"],
        cwd=root, env=env, capture_output=True, text=True, timeout=600,
    )
    combined = result.stdout + result.stderr

    assert result.returncode == 0, (
        "the shipped validator did not pass over a corpus carrying one dangling "
        "reference. Both rules are advisory, so a non-zero exit means something "
        f"other than the reported debt failed:\n{combined}"
    )
    assert _REFERENCE_RULE in combined, (
        f"the real run never mentioned {_REFERENCE_RULE}, so the validator was "
        f"collected but enforced nothing:\n{combined}"
    )
    assert ABSENT_TRAIN in combined, (
        "the run did not name the dangling train it was given, so it produced a "
        f"verdict without having scanned the corpus:\n{combined}"
    )
    assert "github-issue#940002" in combined, (
        "the run reported no per-issue location for the dangling reference, so "
        f"the report is not actionable:\n{combined}"
    )
    assert "github-issue#940001" not in combined, (
        "the run reported the issue whose train RESOLVES, so it is not "
        f"discriminating between the two:\n{combined}"
    )
