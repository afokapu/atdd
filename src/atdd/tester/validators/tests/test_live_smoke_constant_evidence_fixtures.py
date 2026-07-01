# URN: test:govern-lifecycle:live-smoke-execution-enforcement:E060-INTEGRATION-001-detector-fires-on-constant-evidence-harness
# Acceptance: acc:govern-lifecycle:E060-UNIT-001-convention-declares-constant-evidence-rule
# Acceptance: acc:govern-lifecycle:E060-INTEGRATION-001-detector-fires-on-constant-evidence-harness
# Acceptance: acc:govern-lifecycle:E060-SMOKE-001-real-tester-suite-runs-constant-evidence-gate
# WMBT: wmbt:govern-lifecycle:E060
# Phase: SMOKE
# Layer: application
# Runtime: python

"""Coverage for the live-smoke constant-evidence rule (issue #1298, extends #1151).

Proves ``wmbt:govern-lifecycle:E060``:

  - ``conventions/nodes`` declares
    ``tester.acceptance-violation.live-smoke-evidence-must-not-be-constant``
    (strict, severity 4), ``bind_rule()`` resolves it, and its recipe pointer
    names a recipe file that exists (UNIT-001).
  - ``detect_constant_evidence`` flags a harness whose every return is an
    all-constant dict with no assert/raise (the Y002 theater shape) and stays
    silent for a harness that computes evidence or asserts/raises;
    ``evaluate_constant_evidence`` emits exactly one Violation for the
    constant-evidence entry and none for the genuine one (INTEGRATION-001).
  - The real constant-evidence gate runs on this repo, resolves the shipped
    ``execution_kind: live_smoke`` acceptances (R002/D002) to their real
    harnesses, and confirms none return constant evidence (SMOKE-001).

Part of afokapu/atdd-extensions#14.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.tester.validators.test_live_smoke_execution import (
    collect_constant_evidence_violations,
    detect_constant_evidence,
    evaluate_constant_evidence,
)


pytestmark = [pytest.mark.platform]


_RULE_ID = "tester.acceptance-violation.live-smoke-evidence-must-not-be-constant"

# The Y002 theater shape: builds something, returns a fixed dict, never asserts.
_THEATER_HARNESS = '''
def surface_live_smoke():
    cmd = build_launch_argv(policy)
    return {"surfaced": True}
'''

# Genuine: evidence computed from the real outcome.
_COMPUTED_HARNESS = '''
def sigterm_live_smoke():
    proc = spawn_daemon()
    proc.send_signal(SIGTERM)
    return {"exited_cleanly": proc.returncode == 0, "returncode": proc.returncode}
'''

# Genuine: returns a fixed dict but asserts on the real outcome first (can fail).
_ASSERTING_HARNESS = '''
def refused_live_smoke():
    second = spawn_daemon()
    assert second.returncode != 0
    return {"second_refused": True}
'''

# Genuine: raises when the real condition is not met (can fail).
_RAISING_HARNESS = '''
def loop_live_smoke():
    item = wait_for_pending()
    if item is None:
        raise AssertionError("no blocked item appeared")
    return {"resolved": True}
'''


def test_e060_unit_001_convention_declares_constant_evidence_rule() -> None:
    """AC-UNIT-001: the rule binds (strict, sev 4) and its recipe exists."""
    rule = bind_rule(_RULE_ID)
    assert rule.rule_id == _RULE_ID
    assert rule.severity == 4
    assert str(rule.disposition) == "strict" or getattr(rule, "disposition", None) == "strict"
    recipe = (
        Path(__file__).resolve().parents[2]
        / "conventions"
        / "live-smoke-evidence.recipe.yaml"
    )
    assert recipe.is_file(), f"recipe missing: {recipe}"


def test_e060_integration_001_detector_fires_on_constant_evidence_harness() -> None:
    """AC-INTEGRATION-001: theater is flagged; computed/assert/raise are clean."""
    assert detect_constant_evidence(_THEATER_HARNESS, "surface_live_smoke") is not None
    assert detect_constant_evidence(_COMPUTED_HARNESS, "sigterm_live_smoke") is None
    assert detect_constant_evidence(_ASSERTING_HARNESS, "refused_live_smoke") is None
    assert detect_constant_evidence(_RAISING_HARNESS, "loop_live_smoke") is None
    # a missing function or unparseable source never fires
    assert detect_constant_evidence(_THEATER_HARNESS, "not_here") is None
    assert detect_constant_evidence("def (::", "x") is None

    violations = evaluate_constant_evidence(
        [
            (
                "plan/demo/X.yaml:acceptances[0]",
                "acc:demo:X-SMOKE-001",
                [("src/demo/live_smoke.py", "surface_live_smoke", _THEATER_HARNESS)],
            ),
            (
                "plan/demo/X.yaml:acceptances[1]",
                "acc:demo:X-SMOKE-002",
                [("src/demo/live_smoke.py", "sigterm_live_smoke", _COMPUTED_HARNESS)],
            ),
        ]
    )
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_id == _RULE_ID
    assert "acc:demo:X-SMOKE-001" in v.detail
    assert "surface_live_smoke" in v.detail


def test_e060_smoke_001_real_tester_suite_runs_constant_evidence_gate() -> None:
    """AC-SMOKE-001: the real gate resolves shipped live_smoke harnesses and finds them honest.

    Dogfood: walk this repo's real plan/ live_smoke acceptances (R002/D002),
    resolve each to its real harness source, and confirm none return constant
    evidence. Proves the gate is alive on real infra AND the shipped harnesses
    are honest — not a synthetic fixture.
    """
    repo_root = Path(__file__).resolve().parents[5]
    assert (repo_root / "plan").is_dir(), f"repo root not resolved: {repo_root}"

    # The gate must actually resolve at least one real harness — otherwise a
    # zero-violation result would be vacuous (nothing scanned).
    from atdd.tester.validators.test_live_smoke_execution import (
        _harness_calls_in_test,
        _module_to_source_path,
        _LIVE_SMOKE_KIND,
    )
    from atdd.tester.validators._acceptance_walker import (
        acceptance_urn,
        iter_repo_acceptances,
        scan_test_acceptance_headers,
    )

    index = scan_test_acceptance_headers(repo_root)
    resolved_harnesses = 0
    for raw in iter_repo_acceptances(repo_root):
        if raw.body.get("execution_kind") != _LIVE_SMOKE_KIND:
            continue
        urn = acceptance_urn(raw.body)
        for test_file in index.get(urn, []):
            for module, _fn in _harness_calls_in_test(test_file.read_text(encoding="utf-8")):
                if _module_to_source_path(repo_root, module).exists():
                    resolved_harnesses += 1
    assert resolved_harnesses >= 1, "gate resolved no real harness — scan would be vacuous"

    violations = collect_constant_evidence_violations(repo_root)
    assert violations == [], (
        "shipped live_smoke harness returns constant evidence: "
        + "; ".join(v.detail for v in violations)
    )
