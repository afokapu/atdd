# URN: test:govern-lifecycle:hermetic-integration-execution-kind:E005-SMOKE-002-rules-resolve-against-real-registry
# Acceptance: acc:govern-lifecycle:E005-SMOKE-002-rules-resolve-against-real-registry
# WMBT: wmbt:govern-lifecycle:E005
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Smoke: true
# Purpose: Eat-own-dog-food — both #690 rules surface and resolve against the
#          real rebuilt toolkit convention registry via `atdd rules`.

"""E005-SMOKE-002 — verify the two hermetic rules are not orphaned in their
YAML: they surface through ``atdd rules grep`` and resolve through
``atdd rules show`` against the *real* rebuilt convention registry.

Issue #690 declares two strict rules in
``src/atdd/tester/conventions/acceptance-violation.convention.yaml``:

  - ``tester.acceptance-violation.hermetic-fake-must-declare-contract``
  - ``tester.acceptance-violation.hermetic-live-smoke-required-must-have-paired-smoke-acceptance``

The GREEN-phase RED fixtures spawn ``atdd rules`` in subprocesses to prove
the rules resolve; this SMOKE test re-runs that surface against the deployed
CLI and the registry as ``build_registry()`` rebuilds it from the repo root,
asserting the rules carry their ``strict`` disposition and an actionable
``fix_hint``.

"Real infrastructure" for a convention-registry feature is the deployed
``atdd`` CLI plus the live convention YAML — nothing here is mocked. Each
subprocess pins the ``atdd`` package to this worktree (the branch under
test) via ``python -m atdd`` with the worktree ``src/`` on ``PYTHONPATH``.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.smoke]

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

_FAKE_RULE = "tester.acceptance-violation.hermetic-fake-must-declare-contract"
_PAIRING_RULE = (
    "tester.acceptance-violation."
    "hermetic-live-smoke-required-must-have-paired-smoke-acceptance"
)


def _worktree_env() -> dict:
    """Environment that pins the ``atdd`` package to this worktree."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{SRC}{os.pathsep}{existing}" if existing else str(SRC)
    return env


def _run_atdd(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "atdd", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=_worktree_env(),
    )


def test_rules_grep_hermetic_lists_both_new_rule_ids() -> None:
    """`atdd rules grep hermetic` surfaces BOTH new rule_ids from the real
    rebuilt registry."""
    proc = _run_atdd("rules", "grep", "hermetic")
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"atdd rules grep failed:\n{out}"
    assert _FAKE_RULE in out, (
        f"hermetic-fake rule not surfaced by rules grep:\n{out}"
    )
    assert _PAIRING_RULE in out, (
        f"hermetic-live-smoke-pairing rule not surfaced by rules grep:\n{out}"
    )


@pytest.mark.parametrize("rule_id", [_FAKE_RULE, _PAIRING_RULE])
def test_rules_show_resolves_rule_with_strict_disposition_and_fix_hint(
    rule_id: str,
) -> None:
    """`atdd rules show <rule-id>` resolves each new rule against the real
    registry, exits 0, and prints the strict disposition plus a fix_hint —
    never raising RuleNotInRegistryError / AmbiguousRuleError."""
    proc = _run_atdd("rules", "show", rule_id)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"atdd rules show {rule_id} failed:\n{out}"

    assert "RuleNotInRegistryError" not in out, (
        f"rule {rule_id} is orphaned in its YAML — not in the registry:\n{out}"
    )
    assert "AmbiguousRuleError" not in out, (
        f"rule {rule_id} resolved ambiguously:\n{out}"
    )

    assert rule_id in out, f"rules show did not echo the resolved rule_id:\n{out}"
    assert "disposition:" in out and "strict" in out, (
        f"rules show did not print the strict disposition for {rule_id}:\n{out}"
    )
    assert "fix_hint" in out, (
        f"rules show printed no fix_hint for {rule_id}:\n{out}"
    )


def test_rules_show_fix_hint_names_a_recipe_that_exists_on_disk() -> None:
    """The fidelity rule's recipe pointer resolves to a recipe file that
    exists under the real conventions tree (registry ↔ recipe coherence)."""
    proc = _run_atdd("rules", "show", _FAKE_RULE)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "recipe:" in out, f"rules show printed no recipe pointer:\n{out}"

    recipes_dir = SRC / "atdd" / "tester" / "conventions"
    contract_recipe = recipes_dir / "hermetic-integration-contract.recipe.yaml"
    pairing_recipe = recipes_dir / "hermetic-live-smoke-pairing.recipe.yaml"
    assert contract_recipe.is_file(), f"missing recipe file: {contract_recipe}"
    assert pairing_recipe.is_file(), f"missing recipe file: {pairing_recipe}"
    # The fidelity rule's recipe pointer names the contract recipe.
    assert "hermetic-integration-contract" in out, out


__all__ = [
    "test_rules_grep_hermetic_lists_both_new_rule_ids",
    "test_rules_show_resolves_rule_with_strict_disposition_and_fix_hint",
    "test_rules_show_fix_hint_names_a_recipe_that_exists_on_disk",
]
