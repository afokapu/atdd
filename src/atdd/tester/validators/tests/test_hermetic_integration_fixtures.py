# URN: test:govern-lifecycle:hermetic-integration-execution-kind:E005-UNIT-001-convention-declares-hermetic-vocabularies
# Acceptance: acc:govern-lifecycle:E005-UNIT-001-convention-declares-hermetic-vocabularies
# Acceptance: acc:govern-lifecycle:E005-UNIT-002-rules-show-resolves-each-rule
# Acceptance: acc:govern-lifecycle:E005-INTEGRATION-001-fidelity-validator-fires-on-undeclared-fake
# Acceptance: acc:govern-lifecycle:E005-INTEGRATION-002-fidelity-validator-silent-when-no-fakes
# Acceptance: acc:govern-lifecycle:E005-INTEGRATION-003-pairing-validator-fires-on-missing-sibling
# Acceptance: acc:govern-lifecycle:E005-INTEGRATION-004-pairing-validator-silent-when-sibling-present
# Acceptance: acc:govern-lifecycle:E005-INTEGRATION-005-unknown-boundary-kind-rejected
# WMBT: wmbt:govern-lifecycle:E005
# Phase: GREEN
# Layer: application
# Runtime: python

"""RED fixture coverage for the hermetic-integration execution kind (issue #690).

These tests convert the seven GREEN-phase acceptances of
``wmbt:govern-lifecycle:E005`` into failing RED tests. They prove the
substrate that issue #690 ships:

  - ``acceptance.convention.yaml`` declares the orthogonal ``execution_kinds:``
    and ``boundary_kinds:`` vocabularies (UNIT-001).
  - The two new strict rules resolve via ``atdd rules show`` / ``atdd rules
    grep`` and point at recipe files that exist on disk (UNIT-001, UNIT-002).
  - ``evaluate_hermetic_fidelity_declaration`` (the
    ``hermetic-fake-must-declare-contract`` evaluator) fires on a fake-backed
    hermetic acceptance that omits its fidelity declaration, stays silent when
    no fakes are permitted, and rejects unknown boundary vocabulary
    (INTEGRATION-001, -002, -005).
  - ``evaluate_hermetic_live_smoke_pairing`` (the
    ``hermetic-live-smoke-required-must-have-paired-smoke-acceptance``
    evaluator) fires when a ``live_smoke_required: true`` hermetic acceptance
    has no paired ``execution_kind: live_smoke`` sibling under the same WMBT,
    and stays silent when the sibling is present or the flag is false
    (INTEGRATION-003, -004).

RED contract: every test here MUST fail until the coder lands Phase 1
(convention extension), Phase 2 (the two validators + recipes) of #690.
Imports of the not-yet-existing validator modules are performed *inside*
the test bodies so pytest can still collect this file without error.

The two SMOKE-phase acceptances (E005-SMOKE-001, E005-SMOKE-002) are
verified at the GREEN -> SMOKE transition against the real toolkit
(gate tests GT-500/510/520/530), not here.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root


pytestmark = [pytest.mark.platform]


_REPO_ROOT = find_repo_root()

_ACCEPTANCE_CONVENTION = (
    _REPO_ROOT / "src" / "atdd" / "planner" / "conventions" / "acceptance.convention.yaml"
)
_VIOLATION_CONVENTION = (
    _REPO_ROOT
    / "src" / "atdd" / "tester" / "conventions" / "acceptance-violation.convention.yaml"
)
_RECIPE_DIR = _REPO_ROOT / "src" / "atdd" / "tester" / "conventions"

_RULE_FIDELITY = "tester.acceptance-violation.hermetic-fake-must-declare-contract"
_RULE_PAIRING = (
    "tester.acceptance-violation.hermetic-live-smoke-required-must-have-paired-smoke-acceptance"
)

# Controlled boundary vocabulary the convention must declare (Decision #3).
_EXPECTED_BOUNDARY_KINDS = {
    "argv",
    "subprocess",
    "filesystem",
    "git",
    "http_wire",
    "llm_wire",
    "cmux_rpc",
    "env_config",
    "db_wire",
    "event_wire",
}
_EXPECTED_EXECUTION_KINDS = {"hermetic_integration", "live_smoke"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _flatten_vocab(node: Any) -> set:
    """Collect every string leaf from a list/dict/scalar vocabulary node.

    The convention may declare ``execution_kinds:`` / ``boundary_kinds:`` as a
    plain list, or as a mapping of name -> description. This helper accepts
    either shape so the RED test does not over-constrain the coder's choice.
    """
    out: set = set()
    if isinstance(node, str):
        out.add(node)
    elif isinstance(node, list):
        for item in node:
            out |= _flatten_vocab(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            out.add(key)
            out |= _flatten_vocab(value)
    return out


def _run_atdd(*args: str) -> subprocess.CompletedProcess:
    """Invoke the real ``atdd`` CLI from the repo root."""
    return subprocess.run(
        ["atdd", *args],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
    )


def _acc(
    urn: str,
    *,
    execution_kind: str | None = None,
    hermetic: Dict[str, Any] | None = None,
    phase: str = "GREEN",
) -> Dict[str, Any]:
    """Build a synthetic acceptance dict shaped like a plan/ YAML block."""
    body: Dict[str, Any] = {
        "identity": {"urn": urn, "id": urn.split(":")[-1], "phase": phase},
        "harness": {"type": "integration", "category": "backend"},
    }
    if execution_kind is not None:
        body["execution_kind"] = execution_kind
    if hermetic is not None:
        body["hermetic"] = hermetic
    return body


def _wmbt(urn: str, acceptances: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a synthetic WMBT dict carrying an acceptances list."""
    return {"urn": urn, "acceptances": acceptances}


# ===========================================================================
# E005-UNIT-001 — convention declares the hermetic vocabularies
# ===========================================================================
def test_e005_unit_001_convention_declares_hermetic_vocabularies() -> None:
    """acceptance.convention.yaml declares execution_kinds:/boundary_kinds: and
    rules grep surfaces both new rule_ids; existing enums stay intact."""
    data = yaml.safe_load(_ACCEPTANCE_CONVENTION.read_text(encoding="utf-8"))
    assert isinstance(data, dict)

    # New orthogonal execution_kinds: vocabulary (>= hermetic_integration, live_smoke).
    assert "execution_kinds" in data, (
        "acceptance.convention.yaml must declare an 'execution_kinds:' vocabulary"
    )
    execution_kinds = _flatten_vocab(data["execution_kinds"])
    assert _EXPECTED_EXECUTION_KINDS <= execution_kinds, (
        f"execution_kinds missing {_EXPECTED_EXECUTION_KINDS - execution_kinds}"
    )

    # New controlled boundary_kinds: vocabulary (all 10 values, Decision #3).
    assert "boundary_kinds" in data, (
        "acceptance.convention.yaml must declare a 'boundary_kinds:' vocabulary"
    )
    boundary_kinds = _flatten_vocab(data["boundary_kinds"])
    assert _EXPECTED_BOUNDARY_KINDS <= boundary_kinds, (
        f"boundary_kinds missing {_EXPECTED_BOUNDARY_KINDS - boundary_kinds}"
    )
    # Decision #7: golden_output is NOT a boundary_kind (golden is a harness_code).
    assert "golden_output" not in boundary_kinds

    # Existing orthogonal axes remain untouched (Decision #10).
    assert "harness_codes" in data and "golden" in data["harness_codes"]
    assert "harness_types" in data
    for legacy in ("unit", "integration", "e2e"):
        assert legacy in data["harness_types"], f"harness_types lost {legacy!r}"

    # Both new rules are declared in acceptance-violation.convention.yaml.
    violation_data = yaml.safe_load(_VIOLATION_CONVENTION.read_text(encoding="utf-8"))
    declared_rule_ids = {r.get("id") for r in violation_data.get("rules", [])}
    assert _RULE_FIDELITY in declared_rule_ids
    assert _RULE_PAIRING in declared_rule_ids

    # The substrate is discoverable: `atdd rules grep hermetic` lists both.
    result = _run_atdd("rules", "grep", "hermetic")
    assert result.returncode == 0, result.stderr
    assert _RULE_FIDELITY in result.stdout
    assert _RULE_PAIRING in result.stdout


# ===========================================================================
# E005-UNIT-002 — atdd rules show resolves each new rule
# ===========================================================================
@pytest.mark.parametrize(
    ("rule_id", "recipe_file"),
    [
        (_RULE_FIDELITY, "hermetic-integration-contract.recipe.yaml"),
        (_RULE_PAIRING, "hermetic-live-smoke-pairing.recipe.yaml"),
    ],
)
def test_e005_unit_002_rules_show_resolves_each_rule(
    rule_id: str, recipe_file: str
) -> None:
    """`atdd rules show <rule-id>` resolves each new rule, prints the strict
    disposition + fix_hint, and the named recipe file exists on disk."""
    result = _run_atdd("rules", "show", rule_id)
    assert result.returncode == 0, (
        f"`atdd rules show {rule_id}` must exit 0 (no RuleNotInRegistryError / "
        f"AmbiguousRuleError); got {result.returncode}\n{result.stderr}"
    )
    out = result.stdout
    assert rule_id in out
    assert "disposition" in out and "strict" in out
    assert "fix_hint" in out

    # The recipe wiring resolves to a real file under the conventions dir.
    assert (_RECIPE_DIR / recipe_file).is_file(), (
        f"rule {rule_id} must point at recipe file {recipe_file} which must exist"
    )


# ===========================================================================
# E005-INTEGRATION-001 — fidelity validator fires on an undeclared fake
# ===========================================================================
def test_e005_integration_001_fidelity_validator_fires_on_undeclared_fake() -> None:
    """A hermetic acceptance with a non-empty permitted_fakes list but no
    fake_contract_fidelity declaration yields exactly one Violation."""
    from atdd.tester.validators.test_hermetic_integration_contract import (
        evaluate_hermetic_fidelity_declaration,
    )

    path = Path("plan/govern-lifecycle/Z001.yaml")
    bad = _acc(
        "acc:govern-lifecycle:Z001-INTEGRATION-001-cassette-no-fidelity",
        execution_kind="hermetic_integration",
        hermetic={
            "exercised_boundaries": ["http_wire"],
            "permitted_fakes": ["cassette_http"],
            "live_smoke_required": False,
            # fake_contract_fidelity intentionally OMITTED
        },
    )

    violations = evaluate_hermetic_fidelity_declaration([(path, bad)])
    assert len(violations) == 1, f"expected exactly one Violation, got {violations}"
    v = violations[0]
    assert v.rule_id == _RULE_FIDELITY
    assert "acc:govern-lifecycle:Z001-INTEGRATION-001-cassette-no-fidelity" in v.detail
    assert "fake_contract_fidelity" in v.detail

    # A fully-declared hermetic acceptance yields no Violation.
    good = _acc(
        "acc:govern-lifecycle:Z001-INTEGRATION-002-cassette-with-fidelity",
        execution_kind="hermetic_integration",
        hermetic={
            "exercised_boundaries": ["http_wire"],
            "permitted_fakes": ["cassette_http"],
            "fake_contract_fidelity": [
                {
                    "name": "cassette_http",
                    "fidelity": "Recorded method/path/headers/status/body.",
                    "known_gaps": ["Does not prove current auth or provider drift."],
                }
            ],
            "live_smoke_required": True,
        },
    )
    assert evaluate_hermetic_fidelity_declaration([(path, good)]) == []


# ===========================================================================
# E005-INTEGRATION-002 — fidelity validator silent when no fakes are permitted
# ===========================================================================
def test_e005_integration_002_fidelity_validator_silent_when_no_fakes() -> None:
    """The rule fires ONLY when execution_kind == hermetic_integration AND
    permitted_fakes is non-empty; pre-existing acceptances are never flagged."""
    from atdd.tester.validators.test_hermetic_integration_contract import (
        evaluate_hermetic_fidelity_declaration,
    )

    path = Path("plan/govern-lifecycle/Z002.yaml")

    # Acceptance A: hermetic, but permitted_fakes is empty -> rule does not apply.
    acc_a = _acc(
        "acc:govern-lifecycle:Z002-INTEGRATION-001-real-subprocess",
        execution_kind="hermetic_integration",
        hermetic={
            "exercised_boundaries": ["argv", "subprocess", "filesystem"],
            "permitted_fakes": [],
            "live_smoke_required": False,
        },
    )
    # Acceptance B: no execution_kind at all -> backward-compat, never inspected.
    acc_b = _acc("acc:govern-lifecycle:Z002-INTEGRATION-002-legacy-acceptance")

    assert evaluate_hermetic_fidelity_declaration([(path, acc_a), (path, acc_b)]) == []


# ===========================================================================
# E005-INTEGRATION-003 — pairing validator fires on a missing live-smoke sibling
# ===========================================================================
def test_e005_integration_003_pairing_validator_fires_on_missing_sibling() -> None:
    """live_smoke_required: true with no execution_kind: live_smoke sibling
    under the SAME WMBT yields exactly one Violation."""
    from atdd.tester.validators.test_hermetic_live_smoke_pairing import (
        evaluate_hermetic_live_smoke_pairing,
    )

    hermetic_acc = _acc(
        "acc:govern-lifecycle:Z003-INTEGRATION-001-cassette-requires-live",
        execution_kind="hermetic_integration",
        hermetic={
            "exercised_boundaries": ["http_wire"],
            "permitted_fakes": ["cassette_http"],
            "fake_contract_fidelity": [
                {
                    "name": "cassette_http",
                    "fidelity": "Recorded envelope.",
                    "known_gaps": ["No live auth proof."],
                }
            ],
            "live_smoke_required": True,
        },
    )
    wmbt_missing = _wmbt("wmbt:govern-lifecycle:Z003", [hermetic_acc])

    # A live_smoke acceptance under a DIFFERENT WMBT must NOT satisfy the rule.
    other_wmbt = _wmbt(
        "wmbt:govern-lifecycle:Z004",
        [_acc("acc:govern-lifecycle:Z004-E2E-001-live-canary", execution_kind="live_smoke")],
    )

    violations = evaluate_hermetic_live_smoke_pairing(
        [
            (Path("plan/govern-lifecycle/Z003.yaml"), wmbt_missing),
            (Path("plan/govern-lifecycle/Z004.yaml"), other_wmbt),
        ]
    )
    assert len(violations) == 1, f"expected exactly one Violation, got {violations}"
    v = violations[0]
    assert v.rule_id == _RULE_PAIRING
    assert "acc:govern-lifecycle:Z003-INTEGRATION-001-cassette-requires-live" in v.detail
    assert "wmbt:govern-lifecycle:Z003" in v.detail


# ===========================================================================
# E005-INTEGRATION-004 — pairing validator silent when the sibling is present
# ===========================================================================
def test_e005_integration_004_pairing_validator_silent_when_sibling_present() -> None:
    """No Violation when a paired live_smoke sibling exists under the same WMBT,
    or when live_smoke_required is false."""
    from atdd.tester.validators.test_hermetic_live_smoke_pairing import (
        evaluate_hermetic_live_smoke_pairing,
    )

    # WMBT X: hermetic acceptance with live_smoke_required: true + paired sibling.
    wmbt_x = _wmbt(
        "wmbt:govern-lifecycle:Z005",
        [
            _acc(
                "acc:govern-lifecycle:Z005-INTEGRATION-001-cassette",
                execution_kind="hermetic_integration",
                hermetic={
                    "exercised_boundaries": ["http_wire"],
                    "permitted_fakes": ["cassette_http"],
                    "fake_contract_fidelity": [
                        {
                            "name": "cassette_http",
                            "fidelity": "Recorded envelope.",
                            "known_gaps": ["No live auth proof."],
                        }
                    ],
                    "live_smoke_required": True,
                },
            ),
            _acc(
                "acc:govern-lifecycle:Z005-E2E-002-live-canary",
                execution_kind="live_smoke",
            ),
        ],
    )
    # WMBT Y: hermetic acceptance with live_smoke_required: false -> no pairing needed.
    wmbt_y = _wmbt(
        "wmbt:govern-lifecycle:Z006",
        [
            _acc(
                "acc:govern-lifecycle:Z006-INTEGRATION-001-local-git",
                execution_kind="hermetic_integration",
                hermetic={
                    "exercised_boundaries": ["git", "filesystem"],
                    "permitted_fakes": [],
                    "live_smoke_required": False,
                },
            )
        ],
    )

    violations = evaluate_hermetic_live_smoke_pairing(
        [
            (Path("plan/govern-lifecycle/Z005.yaml"), wmbt_x),
            (Path("plan/govern-lifecycle/Z006.yaml"), wmbt_y),
        ]
    )
    assert violations == []


# ===========================================================================
# E005-INTEGRATION-005 — unknown boundary_kind value is rejected
# ===========================================================================
def test_e005_integration_005_unknown_boundary_kind_rejected() -> None:
    """An exercised_boundaries value outside the controlled vocabulary is
    rejected; an all-valid boundary list yields no boundary Violation."""
    from atdd.tester.validators.test_hermetic_integration_contract import (
        evaluate_hermetic_fidelity_declaration,
    )

    path = Path("plan/govern-lifecycle/Z007.yaml")
    fidelity = [
        {
            "name": "cassette_http",
            "fidelity": "Recorded envelope.",
            "known_gaps": ["No live auth proof."],
        }
    ]

    bad_boundary = _acc(
        "acc:govern-lifecycle:Z007-INTEGRATION-001-bogus-boundary",
        execution_kind="hermetic_integration",
        hermetic={
            "exercised_boundaries": ["http_wire", "bogus_socket"],
            "permitted_fakes": ["cassette_http"],
            "fake_contract_fidelity": fidelity,
            "live_smoke_required": False,
        },
    )
    violations = evaluate_hermetic_fidelity_declaration([(path, bad_boundary)])
    assert violations, "an unknown boundary_kind value must produce a Violation"
    boundary_violation = next(
        (v for v in violations if "bogus_socket" in v.detail), None
    )
    assert boundary_violation is not None, (
        f"expected a Violation naming 'bogus_socket', got {violations}"
    )
    # The failure lists the permitted vocabulary so the author can self-correct.
    assert any(known in boundary_violation.detail for known in _EXPECTED_BOUNDARY_KINDS)

    # An acceptance whose boundaries are all in-vocabulary raises no boundary flag.
    valid_boundary = _acc(
        "acc:govern-lifecycle:Z007-INTEGRATION-002-valid-boundary",
        execution_kind="hermetic_integration",
        hermetic={
            "exercised_boundaries": ["http_wire", "subprocess"],
            "permitted_fakes": ["cassette_http"],
            "fake_contract_fidelity": fidelity,
            "live_smoke_required": False,
        },
    )
    assert evaluate_hermetic_fidelity_declaration([(path, valid_boundary)]) == []


__all__ = [
    "test_e005_unit_001_convention_declares_hermetic_vocabularies",
    "test_e005_unit_002_rules_show_resolves_each_rule",
    "test_e005_integration_001_fidelity_validator_fires_on_undeclared_fake",
    "test_e005_integration_002_fidelity_validator_silent_when_no_fakes",
    "test_e005_integration_003_pairing_validator_fires_on_missing_sibling",
    "test_e005_integration_004_pairing_validator_silent_when_sibling_present",
    "test_e005_integration_005_unknown_boundary_kind_rejected",
]
