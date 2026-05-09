# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-001-observer-run-tails-log
# Acceptance: acc:observe-and-correct:P001-UNIT-001-observer-run-tails-log
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: application
"""P001-UNIT-001 — `atdd observer run --agent-id <id>` starts and tails
the agent's `output.log`, watches the worktree, and discovers/loads
detection rules from `.atdd/observer/rules/*.yaml`.

Issue #500 (L1). Spec: `atdd-coach-spec-v9.md` §5.4 / §8.1.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_exposes_observer_class_and_subcommands():
    from atdd.coach.commands import observer

    for name in ("Observer", "RuleRegistry", "Correction", "ObserverRule"):
        assert hasattr(observer, name), f"missing atdd.coach.commands.observer.{name}"

    for name in ("cmd_run", "cmd_attach", "cmd_status", "cmd_aggregate_approve"):
        assert callable(getattr(observer, name, None)), (
            f"missing callable atdd.coach.commands.observer.{name}"
        )

    assert callable(getattr(observer, "main", None))
    assert callable(getattr(observer, "run", None))


# ---------------------------------------------------------------------------
# `cmd_run` integration with the runtime layout
# ---------------------------------------------------------------------------


def test_cmd_run_creates_agent_dir_and_loads_empty_registry(tmp_path: Path):
    """`atdd observer run` for an unknown agent creates the per-agent
    runtime dir and reports no rules loaded — does not raise."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"

    rc = observer.cmd_run(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
        once=True,
    )
    assert rc == 0
    agent_dir = runtime / "agents" / "agent-A"
    assert agent_dir.exists(), "observer must materialize <runtime>/agents/<id>/"


def test_cmd_run_tails_output_log_and_collects_appended_lines(tmp_path: Path):
    """The observer reads new lines appended to `output.log` since the
    last scan (tail behavior, not full-rescan)."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)
    (agent_dir / "output.log").write_text("first line\nsecond line\n")

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=None,
    )
    ctx1 = obs.collect_input()
    assert tuple(ctx1.log_lines) == ("first line", "second line")

    # Append more — second collect must yield ONLY the new lines.
    with (agent_dir / "output.log").open("a") as fh:
        fh.write("third line\n")
    ctx2 = obs.collect_input()
    assert tuple(ctx2.log_lines) == ("third line",), (
        "Observer must tail (offset-aware), not re-emit the whole log."
    )


def test_cmd_run_loads_rules_from_observer_rules_dir(tmp_path: Path):
    """A well-formed YAML rule under `.atdd/observer/rules/` is
    discovered, loaded, and registered."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)

    # A rule_id that already exists in the toolkit registry — so bind_rule
    # resolves cleanly. We don't depend on the rule's actual semantics here.
    rule_yaml = """
rule_id: "coach.orchestration.read-only-git-diagnostics"
trigger:
  type: log_regex
  pattern: ".*never matches in this test.*"
correction_text: "stub correction"
injection_method: "cli-return"
severity: 3
disposition: "advisory"
"""
    (rules_dir / "01-test.yaml").write_text(rule_yaml)

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()
    assert len(obs.registry.rules) == 1
    assert obs.registry.rules[0].rule_id == "coach.orchestration.read-only-git-diagnostics"
    assert obs.registry.load_errors == []


def test_cmd_run_watches_worktree_changes(tmp_path: Path):
    """The observer collects file paths changed in the agent's worktree
    since the last scan."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / "a.txt").write_text("v1")

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=None,
        worktree=worktree,
    )
    obs.collect_input()  # baseline

    (worktree / "a.txt").write_text("v2")
    (worktree / "b.txt").write_text("new")

    ctx2 = obs.collect_input()
    changed = set(ctx2.worktree_changes)
    assert "a.txt" in changed
    assert "b.txt" in changed
