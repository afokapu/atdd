# URN: test:observe-and-correct:observer-runtime-and-rules:M001-SMOKE-001-basic-observer-rules-load-end-to-end
# Acceptance: acc:observe-and-correct:M001-UNIT-008-rules-co-located-as-yaml
# WMBT: wmbt:observe-and-correct:M001
# Phase: SMOKE
# Layer: integration
"""SMOKE M001-001 — End-to-end rule loading against real filesystem.

Issue #506 (L2). Spec: `atdd-coach-spec-v9.md` §8.3.

Drives the production code paths (no internal helpers, no mocks):
  Observer.load_rules() walks `.atdd/observer/rules/` on disk, dispatches
  through RuleRegistry.load_dir() / _build_rule_from_yaml(), and the
  resulting RuleRegistry has 7 rules with zero load_errors.

Then evaluates the loaded rules against a synthetic ObservedInput that
should fire each rule, confirming the integrated registry/dispatcher
path works end-to-end.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


REPO_ROOT = Path(__file__).resolve().parents[5]
RULES_DIR = REPO_ROOT / ".atdd" / "observer" / "rules"


EXPECTED_RULE_IDS = {
    # L2 basic-protocol rules (#506)
    "coach.observer.unstructured-question",
    "coach.observer.token-silence",
    "coach.observer.completion-claim-without-commit",
    "coach.observer.out-of-scope-edit",
    "coach.observer.missed-heartbeat",
    "coach.observer.reviewer-edit-attempt",
    "coach.observer.validator-failure-ignored",
    # M002 — absorbed babysit token-threshold (#507)
    "coach.orchestration.token-threshold",
    # L4 — absorbed-from-babysit python-builder rules (#513;
    # loader regression fixed in #700)
    "coach.observer.bash-auto-approve",
    "coach.observer.canonical-naming-drift",
    "coach.observer.layout-drift",
    "coach.observer.smoke-skip",
}


def test_observer_loads_all_rules_from_real_fs(tmp_path: Path):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    obs = observer.Observer(
        agent_id="agent-smoke",
        runtime_dir=runtime,
        rules_dir=RULES_DIR,
    )
    obs.load_rules()

    assert obs.registry.load_errors == [], (
        f"observer reported load errors: {obs.registry.load_errors}"
    )
    loaded = {r.rule_id for r in obs.registry.rules}
    assert loaded == EXPECTED_RULE_IDS, (
        f"missing/extra rule_ids — loaded={sorted(loaded)} expected={sorted(EXPECTED_RULE_IDS)}"
    )


def test_loaded_rules_evaluate_and_dispatch_corrections(tmp_path: Path):
    """Drive the complete pipeline: load → evaluate → dispatch → persist.

    Constructs a synthetic ObservedInput that should fire several rules,
    runs `scan_once()`, and asserts both the corrections.jsonl and the
    cli-return.jsonl files materialize on disk."""
    import json

    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    obs = observer.Observer(
        agent_id="agent-smoke",
        runtime_dir=runtime,
        rules_dir=RULES_DIR,
    )
    obs.load_rules()
    assert obs.registry.load_errors == []

    # Patch collect_input to inject a synthetic snapshot that triggers
    # rule 01 (unstructured question) + rule 03 (completion claim without
    # commit) + rule 04 (out-of-scope edit) — three independent rules.
    def _synthetic() -> observer.ObservedInput:
        return observer.ObservedInput(
            agent_id="agent-smoke",
            log_lines=(
                "Should I rebase or merge here?",
                "Task complete.",
            ),
            events=(),
            worktree_changes=(".atdd/manifest.yaml",),
            wmbt_target_paths=("src/",),
        )

    obs.collect_input = _synthetic  # type: ignore[assignment]

    corrections = obs.scan_once()
    fired_ids = {c.rule_id for c in corrections}

    assert "coach.observer.unstructured-question" in fired_ids
    assert "coach.observer.completion-claim-without-commit" in fired_ids
    assert "coach.observer.out-of-scope-edit" in fired_ids

    # Persistence side effects.
    cor_path = runtime / "agents" / "agent-smoke" / "corrections.jsonl"
    cli_path = runtime / "agents" / "agent-smoke" / "cli-return.jsonl"
    assert cor_path.exists(), "corrections.jsonl must be written"
    assert cli_path.exists(), "cli-return.jsonl must be written by injection dispatcher"

    persisted = [json.loads(line) for line in cor_path.read_text().splitlines() if line]
    persisted_ids = {p["rule_id"] for p in persisted}
    assert "coach.observer.out-of-scope-edit" in persisted_ids
    # The out-of-scope-edit correction should carry the formatted path.
    out_of_scope = [p for p in persisted if p["rule_id"] == "coach.observer.out-of-scope-edit"]
    assert any(".atdd/manifest.yaml" in p["correction_text"] for p in out_of_scope)
