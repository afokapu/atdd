# URN: test:spawn-agents:isolate-worker-claude-config-dir:E030-UNIT-004-seed-plan-excludes-projects-and-history
# Acceptance: acc:spawn-agents:E030-UNIT-004-seed-plan-excludes-projects-and-history
# WMBT: wmbt:spawn-agents:E030
# Phase: GREEN
# Assertion: behavioral
"""E030-UNIT-004 — single pure derivation of the seed-plan for the isolated
``CLAUDE_CONFIG_DIR``.

RED until ``seed_plan(config_root)`` exists in
``atdd.runtime.agent_control.cmux_launch``. The plan is what makes #1057's
isolation VIABLE: it carries the operator's auth/onboarding/settings into the
per-worker dir (so the worker can run non-interactively) while EXCLUDING
``projects/`` (memory + transcripts — keeping the bleed closed) and the large,
operator-private ``history.jsonl``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coder]

from atdd.runtime.agent_control.cmux_launch import seed_plan


def _fake_operator_root(tmp_path: Path) -> Path:
    root = tmp_path / "operator-claude"
    root.mkdir()
    # auth / onboarding / settings-bearing entries
    (root / "settings.json").write_text("{}", encoding="utf-8")
    (root / ".credentials.json").write_text("{}", encoding="utf-8")
    (root / "statsig").mkdir()
    (root / "statsig" / "cache").write_text("x", encoding="utf-8")
    # memory + transcripts that MUST stay out
    (root / "projects").mkdir()
    proj = root / "projects" / "-Users-x-atdd-main"
    proj.mkdir()
    (proj / "memory").mkdir()
    (proj / "memory" / "MEMORY.md").write_text("operator memory", encoding="utf-8")
    # large operator-private file
    (root / "history.jsonl").write_text('{"h":1}\n', encoding="utf-8")
    return root


def test_plan_includes_non_memory_config_entries(tmp_path: Path):
    plan = seed_plan(_fake_operator_root(tmp_path))
    assert "settings.json" in plan
    assert ".credentials.json" in plan
    assert "statsig" in plan


def test_plan_excludes_projects_entirely(tmp_path: Path):
    plan = seed_plan(_fake_operator_root(tmp_path))
    assert "projects" not in plan, (
        "seed plan must never carry projects/ (memory + transcripts) — that would "
        "reintroduce the #1057 bleed"
    )
    # no nested projects path leaks into the plan either (it is a flat top-level set)
    assert not any("projects" in entry for entry in plan)


def test_plan_excludes_history_jsonl(tmp_path: Path):
    plan = seed_plan(_fake_operator_root(tmp_path))
    assert "history.jsonl" not in plan


def test_plan_is_deterministic_and_side_effect_free(tmp_path: Path):
    root = _fake_operator_root(tmp_path)
    listing_before = sorted(p.name for p in root.iterdir())
    first = seed_plan(root)
    second = seed_plan(root)
    assert first == second, "seed_plan must be deterministic on the same input"
    # planning step performs no writes to the operator root
    assert sorted(p.name for p in root.iterdir()) == listing_before


def test_plan_is_empty_when_root_absent(tmp_path: Path):
    assert seed_plan(tmp_path / "does-not-exist") == []
