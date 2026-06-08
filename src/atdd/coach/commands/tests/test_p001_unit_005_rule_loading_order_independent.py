# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-005-rule-loading-order-independent
# Acceptance: acc:observe-and-correct:P001-UNIT-005-rule-loading-order-independent
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: application
"""P001-UNIT-005 — Rules in `.atdd/observer/rules/` load alphabetically
but evaluation outcome is invariant under reverse load order.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _seed_three_rules(rules_dir: Path) -> None:
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "01-alpha.yaml").write_text(
        """
rule_id: "coach.observer.bash-read-only-git-diagnostics"
trigger:
  type: log_regex
  pattern: ".*ALPHA.*"
correction_text: "alpha"
injection_method: "cli-return"
severity: 3
disposition: "advisory"
"""
    )
    (rules_dir / "02-beta.yaml").write_text(
        """
rule_id: "coach.observer.bash-test-runner-invocations"
trigger:
  type: log_regex
  pattern: ".*BETA.*"
correction_text: "beta"
injection_method: "cli-return"
severity: 3
disposition: "advisory"
"""
    )
    (rules_dir / "03-gamma.yaml").write_text(
        """
rule_id: "coach.observer.bash-read-only-file-inspection"
trigger:
  type: log_regex
  pattern: ".*GAMMA.*"
correction_text: "gamma"
injection_method: "cli-return"
severity: 3
disposition: "advisory"
"""
    )


def test_rules_load_alphabetically(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    _seed_three_rules(rules_dir)

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()
    loaded_ids = [r.rule_id for r in obs.registry.rules]
    assert loaded_ids == [
        "coach.observer.bash-read-only-git-diagnostics",
        "coach.observer.bash-test-runner-invocations",
        "coach.observer.bash-read-only-file-inspection",
    ], f"Rules must load alphabetically by filename, got {loaded_ids}"


def test_evaluation_outcome_is_invariant_under_reverse_order(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime_a = tmp_path / "a" / ".atdd" / "runtime"
    runtime_b = tmp_path / "b" / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    _seed_three_rules(rules_dir)

    log = "ALPHA fires here\nBETA also fires\nGAMMA too\n"

    def _setup(runtime: Path) -> observer.Observer:
        agent_dir = runtime / "agents" / "agent-A"
        agent_dir.mkdir(parents=True)
        (agent_dir / "output.log").write_text(log)
        return observer.Observer(
            agent_id="agent-A",
            runtime_dir=runtime,
            rules_dir=rules_dir,
        )

    obs_alpha = _setup(runtime_a)
    obs_alpha.load_rules()
    cors_alpha = obs_alpha.scan_once()

    obs_reverse = _setup(runtime_b)
    obs_reverse.load_rules()
    obs_reverse.registry.rules.reverse()
    cors_reverse = obs_reverse.scan_once()

    rule_ids_alpha = sorted(c.rule_id for c in cors_alpha)
    rule_ids_reverse = sorted(c.rule_id for c in cors_reverse)
    assert rule_ids_alpha == rule_ids_reverse, (
        f"Reversing rule load order changed which rules fired: "
        f"alpha={rule_ids_alpha} reverse={rule_ids_reverse}"
    )
    # All three rules should fire on this input.
    assert len(rule_ids_alpha) == 3
