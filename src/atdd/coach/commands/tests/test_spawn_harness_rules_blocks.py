# URN: test:spawn-agents:D001:spawn-harness-rules-blocks

import yaml

from atdd.coach.commands.spawn_harness_blocks import (
    render_train_rules_block,
    render_wmbt_rules_block,
)
from atdd.coach.utils.rule_binding import RuleMetadata


def _meta(rule_id: str, **overrides) -> RuleMetadata:
    values = dict(
        rule_id=rule_id,
        description="exercise acceptance rule",
        phase="GREEN",
        disposition="strict",
        severity=2,
        recipe=None,
        introduced_in=None,
        then=("first expectation", "second expectation"),
        fix_hint="fix it",
        bound_acceptance_urn="acc:spawn-agents:D001-UNIT-001-wmbt-rules-renderer-shape",
        source_path=__import__("pathlib").Path("/tmp/D001.yaml"),
        feature_urn="feature:spawn-agents:atdd-spawn-skeleton-and-harness",
        wmbt_urn="wmbt:spawn-agents:D001",
        train_urn="train:0002-coach-drives-lifecycle",
        harness_type="unit",
        signal_metric="pytest_pass",
    )
    values.update(overrides)
    return RuleMetadata(**values)


def test_wmbt_rules_renderer_shape_parses_as_yaml():
    rules = [
        _meta("repo.wmbt.D001.rule-001"),
        _meta("repo.wmbt.D001.rule-002", bound_acceptance_urn="acc:two"),
    ]

    block = render_wmbt_rules_block(rules, coach_phase="GREEN")

    assert yaml.safe_load(yaml.safe_dump({"wmbt_rules": block})) == {
        "wmbt_rules": [
            {
                "wmbt_urn": "wmbt:spawn-agents:D001",
                "rules": [
                    {
                        "id": "repo.wmbt.D001.rule-001",
                        "acceptance_urn": "acc:spawn-agents:D001-UNIT-001-wmbt-rules-renderer-shape",
                        "purpose": "exercise acceptance rule",
                        "expectations": ["first expectation", "second expectation"],
                        "harness_type": "unit",
                        "signal_metric": "pytest_pass",
                    },
                    {
                        "id": "repo.wmbt.D001.rule-002",
                        "acceptance_urn": "acc:two",
                        "purpose": "exercise acceptance rule",
                        "expectations": ["first expectation", "second expectation"],
                        "harness_type": "unit",
                        "signal_metric": "pytest_pass",
                    },
                ],
            }
        ]
    }


def test_train_rules_renderer_shape_parses_as_yaml():
    block = render_train_rules_block(
        [_meta("repo.train.0002.rule-001")], coach_phase="GREEN"
    )

    assert yaml.safe_load(yaml.safe_dump({"train_rules": block})) == {
        "train_rules": [
            {
                "train_urn": "train:0002-coach-drives-lifecycle",
                "rules": [
                    {
                        "id": "repo.train.0002.rule-001",
                        "purpose": "exercise acceptance rule",
                        "expectations": ["first expectation", "second expectation"],
                    }
                ],
            }
        ]
    }


def test_phase_filter_applies_without_placeholders():
    green = _meta("repo.wmbt.D001.green", phase="GREEN")
    smoke = _meta("repo.wmbt.D001.smoke", phase="SMOKE")
    train_smoke = _meta("repo.train.0002.smoke", phase="SMOKE")

    assert render_wmbt_rules_block([green, smoke], coach_phase="GREEN") == [
        {
            "wmbt_urn": "wmbt:spawn-agents:D001",
            "rules": [
                {
                    "id": "repo.wmbt.D001.green",
                    "acceptance_urn": "acc:spawn-agents:D001-UNIT-001-wmbt-rules-renderer-shape",
                    "purpose": "exercise acceptance rule",
                    "expectations": ["first expectation", "second expectation"],
                    "harness_type": "unit",
                    "signal_metric": "pytest_pass",
                }
            ],
        }
    ]
    assert render_train_rules_block([train_smoke], coach_phase="GREEN") == []


def test_mixed_scope_uses_matching_renderer_only():
    wmbt = _meta("repo.wmbt.D001.only", train_urn=None)
    train = _meta("repo.train.0002.only", wmbt_urn=None)

    assert [rule["rules"][0]["id"] for rule in render_wmbt_rules_block([wmbt, train], coach_phase="GREEN")] == ["repo.wmbt.D001.only"]
    assert [rule["rules"][0]["id"] for rule in render_train_rules_block([wmbt, train], coach_phase="GREEN")] == ["repo.train.0002.only"]


def test_empty_scope_omits_block_content():
    assert render_wmbt_rules_block([], coach_phase="GREEN") == []
    assert render_train_rules_block([], coach_phase="GREEN") == []


def test_spawn_prompt_includes_all_three_blocks_in_canonical_order(tmp_path, monkeypatch):
    from atdd.coach.commands import spawn, session_template
    from atdd.coach.commands.tests.test_e001_unit_001_spawn_cli_launches_session import FakeMultiplexer
    from atdd.coach.commands.tests.test_spawn_harness_security_block import _security_meta

    monkeypatch.setattr(
        session_template,
        "fetch_issue",
        lambda n: {"number": n, "title": "t", "body": "body"},
    )

    worktree = tmp_path / "wt"
    worktree.mkdir()
    runtime = tmp_path / "rt"
    rules = [
        _meta("repo.wmbt.D001.green", train_urn=None),
        _meta("repo.wmbt.D001.smoke", phase="SMOKE", train_urn=None),
        _meta("repo.train.0002.green", wmbt_urn=None),
        _security_meta(rule_id="repo.security.green", phase="GREEN"),
    ]

    spawn.cmd_spawn(
        persona="coder",
        llm="claude-code",
        worktree=worktree,
        issue=503,
        agent_id="coder-503-001",
        runtime_root=runtime,
        phase="GREEN",
        multiplexer=FakeMultiplexer(),
        rules=rules,
    )

    content = (worktree / ".launch_prompt.txt").read_text()
    assert content.index("wmbt_rules:") < content.index("train_rules:") < content.index("security_rules:")
    parsed = yaml.safe_load(content[content.index("wmbt_rules:"):])
    assert parsed["wmbt_rules"][0]["rules"][0]["id"] == "repo.wmbt.D001.green"
    assert "repo.wmbt.D001.smoke" not in content
    assert parsed["train_rules"][0]["rules"][0]["id"] == "repo.train.0002.green"
    assert parsed["security_rules"][0]["rules"][0]["id"] == "repo.security.green"
