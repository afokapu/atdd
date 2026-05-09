# URN: test:drive-state-machine:coach-state-machine-and-runtime:D001-UNIT-002-flag-parsing
# Acceptance: acc:drive-state-machine:D001-UNIT-002-flag-parsing
# WMBT: wmbt:drive-state-machine:D001
# Phase: RED
# Layer: application
"""D001-UNIT-002 — every spec §5.1 flag parses; unknown flags raise.

Spec §5.1 surface (verbatim from #496 issue body):

    --max-retries, --escalation-channel, --multiplexer, --multiplexer-mode,
    --auto-merge, --strict-deps, --llm,
    --persona-llm tester=...,coder=...,reviewer=...,
    --judge-llm, --require-issue-review {warn|block|auto},
    --review-phases planned,red,green,smoke,refactor,
    --skip-review, --risk-threshold-block N, --allow-stale-suppressions,
    --resume <run-id>, --dry-run

`--persona-llm` parses to a per-persona dict; `--review-phases` parses to
the enabled-phases set.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]


def _parse(*argv):
    from atdd.coach.commands.coach import parse_cli
    return parse_cli(list(argv))


def test_minimal_invocation_parses():
    cfg = _parse("358")
    assert cfg.issue_numbers == [358]
    assert cfg.dry_run is False
    assert cfg.strict_deps is False


def test_max_retries_parses_int():
    cfg = _parse("358", "--max-retries", "5")
    assert cfg.max_retries == 5


def test_escalation_channel_parses_str():
    cfg = _parse("358", "--escalation-channel", "slack:#oncall")
    assert cfg.escalation_channel == "slack:#oncall"


def test_multiplexer_parses_choice():
    cfg = _parse("358", "--multiplexer", "cmux")
    assert cfg.multiplexer == "cmux"


def test_multiplexer_mode_parses_choice():
    cfg = _parse("358", "--multiplexer-mode", "pane")
    assert cfg.multiplexer_mode == "pane"


def test_auto_merge_is_boolean_flag():
    cfg = _parse("358", "--auto-merge")
    assert cfg.auto_merge is True


def test_strict_deps_is_boolean_flag():
    cfg = _parse("358", "--strict-deps")
    assert cfg.strict_deps is True


def test_llm_parses_default_model():
    cfg = _parse("358", "--llm", "claude-opus-4-7")
    assert cfg.llm == "claude-opus-4-7"


def test_persona_llm_parses_into_per_persona_dict():
    cfg = _parse(
        "358",
        "--persona-llm", "tester=claude-code,coder=codex,reviewer=gpt-5",
    )
    assert cfg.persona_llm == {
        "tester": "claude-code",
        "coder": "codex",
        "reviewer": "gpt-5",
    }


def test_persona_llm_rejects_malformed_value():
    from atdd.coach.commands.coach import parse_cli

    with pytest.raises(SystemExit):
        parse_cli(["358", "--persona-llm", "tester-claude-code"])


def test_judge_llm_parses_str():
    cfg = _parse("358", "--judge-llm", "gpt-5")
    assert cfg.judge_llm == "gpt-5"


def test_require_issue_review_parses_choice():
    for choice in ("warn", "block", "auto"):
        cfg = _parse("358", "--require-issue-review", choice)
        assert cfg.require_issue_review == choice


def test_require_issue_review_rejects_unknown_choice():
    from atdd.coach.commands.coach import parse_cli

    with pytest.raises(SystemExit):
        parse_cli(["358", "--require-issue-review", "loud"])


def test_review_phases_parses_into_enabled_set():
    cfg = _parse("358", "--review-phases", "planned,red,green,smoke,refactor")
    assert cfg.review_phases == {"planned", "red", "green", "smoke", "refactor"}


def test_review_phases_subset_parses():
    cfg = _parse("358", "--review-phases", "planned,green")
    assert cfg.review_phases == {"planned", "green"}


def test_skip_review_is_boolean_flag():
    cfg = _parse("358", "--skip-review")
    assert cfg.skip_review is True


def test_risk_threshold_block_parses_int():
    cfg = _parse("358", "--risk-threshold-block", "7")
    assert cfg.risk_threshold_block == 7


def test_allow_stale_suppressions_is_boolean_flag():
    cfg = _parse("358", "--allow-stale-suppressions")
    assert cfg.allow_stale_suppressions is True


def test_resume_parses_run_id():
    cfg = _parse("358", "--resume", "run-2026-05-09-abc123")
    assert cfg.resume == "run-2026-05-09-abc123"


def test_dry_run_is_boolean_flag():
    cfg = _parse("358", "--dry-run")
    assert cfg.dry_run is True


def test_unknown_flag_raises_systemexit():
    from atdd.coach.commands.coach import parse_cli

    with pytest.raises(SystemExit):
        parse_cli(["358", "--this-flag-does-not-exist"])


def test_resolved_configuration_is_printable():
    """The Config dataclass must be dumpable for inspection (acceptance)."""
    cfg = _parse(
        "358",
        "--strict-deps",
        "--persona-llm", "tester=a,coder=b,reviewer=c",
        "--review-phases", "planned,red",
    )
    rendered = str(cfg)
    assert "358" in rendered
    assert "strict_deps" in rendered or "True" in rendered
    assert "persona_llm" in rendered or "tester" in rendered
