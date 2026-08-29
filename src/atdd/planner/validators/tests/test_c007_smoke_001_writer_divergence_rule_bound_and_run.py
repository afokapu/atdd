# URN: test:author-plan-substrate:author-contract:C007-SMOKE-001-writer-divergence-rule-bound-and-run
# Acceptance: acc:author-plan-substrate:C007-SMOKE-001-writer-divergence-rule-bound-and-run
# WMBT: wmbt:author-plan-substrate:C007
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C007-SMOKE-001 — WRITER-DIVERGENCE is BOUND and RUNS on the live corpus.

Two sides, both executed against the real repo (#1151: a smoke must execute,
not skip, and not assert about a run it never made):

* Registry side — ``planner.contract.registry-coherence`` resolves through
  ``bind_rule``, and the convention node it resolves to actually declares the
  fourth invariant. This is the bidirectional binding contract: a validator may
  not enforce a constraint its rule does not state.
* Enforcement side — the real validator is executed in a subprocess over the
  live ``plan/`` graph and ``contracts/`` registries, and its output names the
  divergences. ``commons:error:response`` is the load-bearing case: its producer
  is marked ``to: external``, so invariant 3 (UNCONSUMED) cannot see it, and
  only WRITER-DIVERGENCE catches that the registry declares a consumer the
  wagon graph does not have.

The disposition is ``advisory``, so the live scan reports rather than blocks:
the subprocess is expected to exit 0 while still emitting the findings.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule

_RULE_ID = "planner.contract.registry-coherence"
_NODE = (
    "src/atdd/planner/conventions/nodes/"
    "planner.contract.registry-coherence.convention.yaml"
)
_VALIDATOR = "src/atdd/planner/validators/test_contract_registry_coherence.py"
_LIVE_TEST = f"{_VALIDATOR}::test_contract_registry_coherence"


def test_writer_divergence_rule_is_bound_and_runs_on_live_corpus() -> None:
    repo_root: Path = find_repo_root()

    # --- Registry side: the bound rule states the invariant the validator enforces.
    rule = bind_rule(_RULE_ID)
    assert rule.rule_id == _RULE_ID
    assert rule.disposition == "advisory", rule.disposition

    node = yaml.safe_load((repo_root / _NODE).read_text(encoding="utf-8"))
    # One legacy constraint embeds a bare "contract:" and so round-trips as a
    # mapping rather than a string; compare over the rendered text instead.
    constraints = yaml.safe_dump(node["content"]["constraints"])
    normative = node["content"]["normative_text"]
    assert "WRITER-DIVERGENCE" in normative, normative
    assert "exactly one producing wagon" in constraints, constraints
    assert "declared producers" in constraints, constraints
    assert "declared consumers" in constraints, constraints

    # --- Enforcement side: really run the validator over the real corpus.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", _LIVE_TEST, "-q", "-p", "no:cacheprovider"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = proc.stdout + proc.stderr

    # Advisory: the debt is reported, the gate does not block.
    assert proc.returncode == 0, out

    # The invariant fired, on the real graph, for each divergence class.
    assert "exactly one producing wagon" in out, out
    assert "registry declares producer(s)" in out, out
    assert "registry declares consumer(s)" in out, out

    # The escape-hatch case invariant 3 structurally cannot catch.
    assert "commons:error:response" in out, out
