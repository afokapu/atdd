# URN: test:observe-and-correct:observer-runtime-and-rules:P001-UNIT-006-rule-load-error-surfaced
# Acceptance: acc:observe-and-correct:P001-UNIT-006-rule-load-error-surfaced
# WMBT: wmbt:observe-and-correct:P001
# Phase: RED
# Layer: application
"""P001-UNIT-006 — A malformed rule emits a one-time stderr warning AND
appends a `corrections.jsonl` entry with `meta: rule_load_error`
referencing the rule path; the observer continues with remaining
well-formed rules.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def test_malformed_rule_warns_to_stderr_and_records_meta_load_error(
    tmp_path: Path, capsys
):
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)

    # Malformed: the YAML parses but is missing rule_id.
    (rules_dir / "00-broken.yaml").write_text(
        """
trigger:
  type: log_regex
  pattern: ".*broken.*"
correction_text: "missing rule_id"
"""
    )
    # A well-formed companion that must continue to load.
    (rules_dir / "01-good.yaml").write_text(
        """
rule_id: "coach.observer.bash-read-only-git-diagnostics"
trigger:
  type: log_regex
  pattern: ".*never matches.*"
correction_text: "stub"
injection_method: "cli-return"
severity: 3
disposition: "advisory"
"""
    )

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()

    # The well-formed rule must be loaded.
    loaded_ids = [r.rule_id for r in obs.registry.rules]
    assert (
        "coach.observer.bash-read-only-git-diagnostics" in loaded_ids
    ), "Well-formed sibling rules must continue to load"

    # The malformed rule must surface as a load error.
    paths = [str(err.path) for err in obs.registry.load_errors]
    assert any("00-broken.yaml" in p for p in paths), (
        f"Malformed rule must be captured in load_errors, got {paths}"
    )

    # stderr warning identifies the rule file.
    err = capsys.readouterr().err
    assert "00-broken.yaml" in err, "stderr warning must reference the rule file"

    # corrections.jsonl entry with meta: rule_load_error.
    cor_path = runtime / "agents" / "agent-A" / "corrections.jsonl"
    assert cor_path.exists(), (
        "Load errors must surface as a meta record in corrections.jsonl"
    )
    records = _read_jsonl(cor_path)
    meta_recs = [r for r in records if r.get("meta") == "rule_load_error"]
    assert len(meta_recs) >= 1
    assert any("00-broken.yaml" in r.get("rule_path", "") for r in meta_recs)


def test_unbindable_rule_id_is_treated_as_load_error(tmp_path: Path, capsys):
    """A rule whose rule_id does not resolve via bind_rule() is captured
    as a load error rather than crashing the observer."""
    from atdd.coach.commands import observer

    runtime = tmp_path / ".atdd" / "runtime"
    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True)

    (rules_dir / "00-unbindable.yaml").write_text(
        """
rule_id: "this.does.not-exist-anywhere-in-registry"
trigger:
  type: log_regex
  pattern: ".*xyz.*"
correction_text: "stub"
injection_method: "cli-return"
severity: 3
disposition: "advisory"
"""
    )

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()
    assert obs.registry.rules == []
    assert len(obs.registry.load_errors) == 1
    cor_path = runtime / "agents" / "agent-A" / "corrections.jsonl"
    assert cor_path.exists()
    recs = _read_jsonl(cor_path)
    assert any(r.get("meta") == "rule_load_error" for r in recs)
