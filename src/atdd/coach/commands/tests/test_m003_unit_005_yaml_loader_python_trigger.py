# URN: test:observe-and-correct:observer-runtime-and-rules:M003-UNIT-005-yaml-loader-python-trigger
# Acceptance: acc:observe-and-correct:M003-UNIT-001-rule-13-bash-auto-approve  (loader integration)
# WMBT: wmbt:observe-and-correct:M003
# Phase: RED
# Layer: application
"""M003-UNIT-005 — Observer YAML loader supports the ``python`` trigger
type, which delegates rule construction to a ``module:attr`` builder.

This is the wire-up that lets the four absorbed-from-babysit rules
(13–16) declare themselves as YAML files at ``.atdd/observer/rules/``
without re-implementing their predicates as regexes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.commands import observer

pytestmark = [pytest.mark.platform]


def test_python_trigger_invokes_module_builder_and_registers_rule(tmp_path: Path):
    """A YAML file with ``trigger.type: python`` and ``builder: module:attr``
    must invoke the module's builder and register the returned ObserverRule."""
    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)

    (rules_dir / "16-smoke-skip.yaml").write_text(
        "trigger:\n"
        "  type: python\n"
        "  builder: 'atdd.coach.observer_rules.smoke_skip:build_rule'\n"
    )

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()
    assert obs.registry.load_errors == []
    assert len(obs.registry.rules) == 1
    assert obs.registry.rules[0].rule_id == "coach.observer.smoke-skip"


def test_python_trigger_missing_builder_field_is_load_error(tmp_path: Path):
    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)

    (rules_dir / "bad.yaml").write_text("trigger:\n  type: python\n")

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()
    assert obs.registry.rules == []
    assert len(obs.registry.load_errors) == 1
    assert "builder" in obs.registry.load_errors[0].reason


def test_python_trigger_unresolvable_callable_is_load_error(tmp_path: Path):
    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)

    (rules_dir / "bad.yaml").write_text(
        "trigger:\n"
        "  type: python\n"
        "  builder: 'atdd.coach.observer_rules.smoke_skip:does_not_exist'\n"
    )

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()
    assert obs.registry.rules == []
    assert len(obs.registry.load_errors) == 1


def test_observer_rules_dir_at_repo_root_loads_all_four_l4_rules():
    """Smoke check that the four YAML files this issue introduces are
    well-formed and register through the loader."""
    import atdd as _atdd

    # Locate this repo's .atdd/observer/rules — the ones #513 ships.
    repo_root = Path(_atdd.__file__).resolve().parent.parent.parent
    candidate_dirs = [
        repo_root / ".atdd" / "observer" / "rules",
        repo_root.parent / ".atdd" / "observer" / "rules",
    ]
    rules_dir = next((d for d in candidate_dirs if d.is_dir()), None)
    if rules_dir is None:
        pytest.skip("repo .atdd/observer/rules not present in installed layout")

    expected = {
        "coach.observer.bash-auto-approve",
        "coach.observer.canonical-naming-drift",
        "coach.observer.layout-drift",
        "coach.observer.smoke-skip",
    }
    yaml_files = {p.stem for p in rules_dir.glob("*.yaml")}
    needed_yaml = {
        "13-bash-auto-approve",
        "14-canonical-naming-drift",
        "15-layout-drift",
        "16-smoke-skip",
    }
    if not needed_yaml.issubset(yaml_files):
        pytest.skip(
            f"#513 YAML rule files not in this layout: missing {needed_yaml - yaml_files}"
        )

    registry = observer.RuleRegistry()
    registry.load_dir(rules_dir)
    loaded_ids = {r.rule_id for r in registry.rules}
    assert expected.issubset(loaded_ids), (
        f"missing rules: {expected - loaded_ids}; load_errors: {registry.load_errors}"
    )
