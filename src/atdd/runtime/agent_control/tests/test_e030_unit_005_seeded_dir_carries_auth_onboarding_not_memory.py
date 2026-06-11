# URN: test:spawn-agents:isolate-worker-claude-config-dir:E030-UNIT-005-seeded-dir-carries-auth-onboarding-not-memory
# Acceptance: acc:spawn-agents:E030-UNIT-005-seeded-dir-carries-auth-onboarding-not-memory
# WMBT: wmbt:spawn-agents:E030
# Phase: GREEN
# Assertion: behavioral
"""E030-UNIT-005 — applying the seed populates the isolated config dir with the
operator's non-memory config while leaving ``projects/`` fresh; idempotent.

RED until ``seed_isolated_config_dir(config_dir, config_root)`` exists in
``atdd.runtime.agent_control.cmux_launch``. After seeding, the worker can resolve
the operator's auth/onboarding/settings inside the isolated dir (so it boots into
its task, not the login screen), yet its ``projects/`` (memory + transcripts)
starts fresh — preserving the #1057 guarantee.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coder]

from atdd.runtime.agent_control.cmux_launch import seed_isolated_config_dir


def _fake_operator_root(tmp_path: Path) -> Path:
    root = tmp_path / "operator-claude"
    root.mkdir()
    (root / "settings.json").write_text('{"theme":"dark"}', encoding="utf-8")
    (root / ".credentials.json").write_text('{"token":"abc"}', encoding="utf-8")
    (root / "statsig").mkdir()
    (root / "statsig" / "cache").write_text("x", encoding="utf-8")
    proj = root / "projects" / "-Users-x-atdd-main" / "memory"
    proj.mkdir(parents=True)
    (proj / "MEMORY.md").write_text("operator memory", encoding="utf-8")
    (root / "history.jsonl").write_text('{"h":1}\n', encoding="utf-8")
    return root


def test_seeded_dir_resolves_operator_non_memory_config(tmp_path: Path):
    root = _fake_operator_root(tmp_path)
    isolated = tmp_path / "worker" / "claude-home"

    seed_isolated_config_dir(isolated, root)

    # settings + credentials are resolvable inside the isolated dir
    assert (isolated / "settings.json").exists()
    assert (isolated / "settings.json").read_text(encoding="utf-8") == '{"theme":"dark"}'
    assert (isolated / ".credentials.json").exists()
    assert (isolated / "statsig" / "cache").exists()


def test_seeded_dir_has_no_operator_memory(tmp_path: Path):
    root = _fake_operator_root(tmp_path)
    isolated = tmp_path / "worker" / "claude-home"

    seed_isolated_config_dir(isolated, root)

    # the operator's memory file is NOT reachable through the isolated projects path
    leaked = isolated / "projects" / "-Users-x-atdd-main" / "memory" / "MEMORY.md"
    assert not leaked.exists(), (
        f"operator memory leaked into the isolated dir at {leaked} — #1057 guarantee broken"
    )
    # projects/ is not seeded at all (memory starts fresh)
    assert not (isolated / "projects").exists()


def test_seeded_dir_omits_history_jsonl(tmp_path: Path):
    root = _fake_operator_root(tmp_path)
    isolated = tmp_path / "worker" / "claude-home"

    seed_isolated_config_dir(isolated, root)

    assert not (isolated / "history.jsonl").exists()


def test_seed_is_idempotent(tmp_path: Path):
    root = _fake_operator_root(tmp_path)
    isolated = tmp_path / "worker" / "claude-home"

    seed_isolated_config_dir(isolated, root)
    before = sorted(p.name for p in isolated.iterdir())
    # second invocation must not raise and must leave the dir in the same state
    seed_isolated_config_dir(isolated, root)
    after = sorted(p.name for p in isolated.iterdir())

    assert before == after
    assert (isolated / "settings.json").read_text(encoding="utf-8") == '{"theme":"dark"}'
