"""
Unit tests for atdd.coach.utils.coach_config.

URN: urn:atdd:test:coach:utils:coach_config
WMBT: wmbt:discover-and-decommission:P002
Acceptances:
  - acc:discover-and-decommission:P002-UNIT-001-load-atdd-config-parses-coach-block
  - acc:discover-and-decommission:P002-UNIT-002-invalid-fields-raise-loud-errors

Coach v9 reads `.atdd/config.yaml::coach` once at startup. Spec §10
documents every field and its default; this parser materializes that
schema as an immutable `CoachConfig` value object and refuses any
deviation from the schema (unknown keys, wrong types, out-of-range
numbers, unknown enum values) with loud errors that cite spec §10.

The strict-unknown-key policy is the inverse of the substrate's
flexible-by-design YAML loaders. Coach config is closed-schema (every
valid key is named in spec §10); a typo like `risk_threshhold.green`
must surface as a config error at load time, not silently inherit the
default and surface as wrong-phase behavior hours later.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.coach_config import (
    CoachConfig,
    CoachConfigError,
    load_coach_config,
    load_coach_config_from_dict,
)


pytestmark = [pytest.mark.platform]


# ============================================================================
# AC-UNIT-001: defaults applied per spec §10
# ============================================================================


class TestEmptyCoachBlockAppliesAllDefaults:
    """An empty coach: block returns a CoachConfig populated with every
    spec §10 default. Reference values are quoted from the issue body /
    spec §10."""

    def test_empty_dict_returns_coach_config(self):
        cfg = load_coach_config_from_dict({})
        assert isinstance(cfg, CoachConfig)

    def test_missing_coach_key_returns_coach_config_with_defaults(self):
        cfg = load_coach_config_from_dict({"version": "1.0"})
        assert cfg.default_llm == "claude-code"

    def test_explicit_empty_coach_block_returns_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.default_llm == "claude-code"

    def test_default_llm_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.default_llm == "claude-code"
        assert cfg.judge_llm == "claude-haiku"

    def test_persona_llm_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.persona_llm["planner"] == "claude-code"
        assert cfg.persona_llm["tester"] == "claude-code"
        assert cfg.persona_llm["coder"] == "claude-code"
        assert cfg.persona_llm["reviewer"] == "gpt-5"

    def test_observer_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.observer.activity_silence_seconds == 90
        assert cfg.observer.process_silence_seconds == 30
        assert cfg.observer.rules_dir == ".atdd/observer/rules"

    def test_review_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.review.enabled is True
        assert cfg.review.phases == ["planned", "red", "green", "smoke"]
        assert cfg.review.same_model_warning is True
        assert cfg.review.same_model_allowed is False

    def test_validators_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.validators.enabled is True
        assert cfg.validators.grace_window_seconds == 30
        assert cfg.validators.selection == "default"
        assert cfg.validators.pytest_args == ["-x", "--tb=short"]

    def test_suppressions_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.suppressions.honor is True
        assert cfg.suppressions.block_on_stale is True
        assert cfg.suppressions.grace_days == 7

    def test_risk_thresholds_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.risk_thresholds.planned is None
        assert cfg.risk_thresholds.red is None
        assert cfg.risk_thresholds.green == 10
        assert cfg.risk_thresholds.smoke == 15
        assert cfg.risk_thresholds.refactor == 5
        assert cfg.risk_thresholds.complete == 0

    def test_judge_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.judge.enabled is True
        assert cfg.judge.fail_open is False
        assert cfg.judge.log_full_inputs is False

    def test_issue_review_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.issue_review.passes == 3
        assert cfg.issue_review.llms == ["claude-haiku", "gpt-5-mini", "gemini-flash"]
        assert cfg.issue_review.dimensions == [
            "systemic", "ambiguities", "gap", "regression", "comprehensiveness"
        ]
        assert cfg.issue_review.require_for_coach == "warn"
        assert cfg.issue_review.stale_after_days == 14

    def test_escalation_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.escalation.channel == "file"
        assert cfg.escalation.slack_webhook is None
        assert cfg.escalation.github_label == "coach-escalation"

    def test_retries_defaults(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.retries.per_state_machine == 3
        assert cfg.retries.per_agent == 2

    def test_token_alert_threshold_default(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        assert cfg.token_alert_threshold == 400000


class TestPartialOverridesMergeWithDefaults:
    """Overridden fields take effect; unmentioned fields fall back to
    spec §10 defaults. Tested at every nesting level."""

    def test_top_level_override(self):
        cfg = load_coach_config_from_dict({
            "coach": {"default_llm": "claude-haiku"}
        })
        assert cfg.default_llm == "claude-haiku"
        # unspecified fields remain at default
        assert cfg.judge_llm == "claude-haiku"  # also default value (coincidence)
        assert cfg.token_alert_threshold == 400000

    def test_persona_llm_partial_override(self):
        cfg = load_coach_config_from_dict({
            "coach": {"persona_llm": {"reviewer": "gpt-5-mini"}}
        })
        assert cfg.persona_llm["reviewer"] == "gpt-5-mini"
        # other personas keep defaults
        assert cfg.persona_llm["planner"] == "claude-code"

    def test_risk_thresholds_partial_override(self):
        cfg = load_coach_config_from_dict({
            "coach": {"risk_thresholds": {"green": 25}}
        })
        assert cfg.risk_thresholds.green == 25
        # other thresholds keep defaults
        assert cfg.risk_thresholds.smoke == 15
        assert cfg.risk_thresholds.complete == 0
        assert cfg.risk_thresholds.planned is None

    def test_validators_partial_override(self):
        cfg = load_coach_config_from_dict({
            "coach": {"validators": {"pytest_args": ["-v"]}}
        })
        assert cfg.validators.pytest_args == ["-v"]
        assert cfg.validators.grace_window_seconds == 30
        assert cfg.validators.enabled is True

    def test_observer_partial_override(self):
        cfg = load_coach_config_from_dict({
            "coach": {"observer": {"activity_silence_seconds": 120}}
        })
        assert cfg.observer.activity_silence_seconds == 120
        assert cfg.observer.process_silence_seconds == 30


class TestNullablesAcceptNull:
    """Null is allowed where spec §10 lists it: risk_thresholds.planned/red
    and escalation.slack_webhook."""

    def test_risk_thresholds_planned_accepts_null(self):
        cfg = load_coach_config_from_dict({
            "coach": {"risk_thresholds": {"planned": None}}
        })
        assert cfg.risk_thresholds.planned is None

    def test_risk_thresholds_red_accepts_null(self):
        cfg = load_coach_config_from_dict({
            "coach": {"risk_thresholds": {"red": None}}
        })
        assert cfg.risk_thresholds.red is None

    def test_risk_thresholds_green_accepts_null(self):
        # Spec lists null in risk_thresholds; permitted across all phases.
        cfg = load_coach_config_from_dict({
            "coach": {"risk_thresholds": {"green": None}}
        })
        assert cfg.risk_thresholds.green is None

    def test_escalation_slack_webhook_accepts_null(self):
        cfg = load_coach_config_from_dict({
            "coach": {"escalation": {"slack_webhook": None}}
        })
        assert cfg.escalation.slack_webhook is None


class TestCoachConfigImmutability:
    """The CoachConfig value object is immutable — coach reads it once
    at startup and consumes it everywhere as a single source of truth."""

    def test_cannot_assign_top_level_field(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        with pytest.raises((AttributeError, TypeError)):
            cfg.default_llm = "claude-haiku"

    def test_cannot_assign_nested_field(self):
        cfg = load_coach_config_from_dict({"coach": {}})
        with pytest.raises((AttributeError, TypeError)):
            cfg.observer.activity_silence_seconds = 999


class TestLoadFromYamlFile:
    """End-to-end: load_coach_config reads .atdd/config.yaml and parses
    the coach.* block."""

    def test_load_from_repo_root_with_coach_block(self, tmp_path: Path):
        atdd_dir = tmp_path / ".atdd"
        atdd_dir.mkdir()
        (atdd_dir / "config.yaml").write_text(yaml.safe_dump({
            "version": "1.0",
            "coach": {"default_llm": "claude-haiku"},
        }))
        cfg = load_coach_config(tmp_path)
        assert cfg.default_llm == "claude-haiku"
        assert cfg.judge_llm == "claude-haiku"  # default

    def test_load_from_repo_root_without_config_returns_defaults(self, tmp_path: Path):
        cfg = load_coach_config(tmp_path)
        assert cfg.default_llm == "claude-code"


# ============================================================================
# AC-UNIT-002: invalid fields raise loud errors
# ============================================================================


class TestUnknownKeysRaiseLoudly:
    """Unknown top-level keys under coach.* must fail loudly. Typos like
    `risk_threshhold` (note doubled-h) must not silently inherit defaults."""

    def test_unknown_top_level_key_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"risk_threshhold": {"green": 10}}
            })
        msg = str(exc_info.value)
        assert "risk_threshhold" in msg
        assert "§10" in msg

    def test_unknown_observer_key_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"observer": {"silence_seconds": 90}}
            })
        msg = str(exc_info.value)
        assert "silence_seconds" in msg
        assert "observer" in msg
        assert "§10" in msg

    def test_unknown_review_key_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"review": {"phazes": ["red"]}}
            })
        assert "phazes" in str(exc_info.value)

    def test_unknown_risk_thresholds_phase_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"risk_thresholds": {"obsolete": 5}}
            })
        assert "obsolete" in str(exc_info.value)
        assert "risk_thresholds" in str(exc_info.value)

    def test_unknown_persona_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"persona_llm": {"orchestrator": "gpt-5"}}
            })
        assert "orchestrator" in str(exc_info.value)


class TestInvalidTypesRaiseLoudly:
    """Wrong types name the offending key and the expected type."""

    def test_default_llm_must_be_string(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({"coach": {"default_llm": 42}})
        msg = str(exc_info.value)
        assert "default_llm" in msg
        assert "string" in msg.lower() or "str" in msg.lower()

    def test_judge_enabled_must_be_bool(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"judge": {"enabled": "yes"}}
            })
        msg = str(exc_info.value)
        assert "judge.enabled" in msg or "enabled" in msg
        assert "bool" in msg.lower()

    def test_observer_seconds_must_be_int(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"observer": {"activity_silence_seconds": "ninety"}}
            })
        msg = str(exc_info.value)
        assert "activity_silence_seconds" in msg
        assert "int" in msg.lower()

    def test_review_phases_must_be_list(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"review": {"phases": "red"}}
            })
        msg = str(exc_info.value)
        assert "phases" in msg
        assert "list" in msg.lower()

    def test_pytest_args_must_be_list_of_strings(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"validators": {"pytest_args": ["-x", 42]}}
            })
        msg = str(exc_info.value)
        assert "pytest_args" in msg

    def test_token_alert_threshold_must_be_int(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"token_alert_threshold": "400k"}
            })
        msg = str(exc_info.value)
        assert "token_alert_threshold" in msg

    def test_risk_threshold_must_be_int_or_null(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"risk_thresholds": {"green": "ten"}}
            })
        msg = str(exc_info.value)
        assert "risk_thresholds.green" in msg or "green" in msg


class TestOutOfRangeRaiseLoudly:
    """Risk thresholds non-negative; seconds non-negative; counts non-negative."""

    def test_risk_threshold_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"risk_thresholds": {"green": -1}}
            })
        msg = str(exc_info.value)
        assert "green" in msg
        assert "non-negative" in msg.lower() or ">= 0" in msg or "negative" in msg.lower()

    def test_observer_activity_silence_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"observer": {"activity_silence_seconds": -5}}
            })
        assert "activity_silence_seconds" in str(exc_info.value)

    def test_observer_process_silence_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"observer": {"process_silence_seconds": -1}}
            })
        assert "process_silence_seconds" in str(exc_info.value)

    def test_validators_grace_window_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"validators": {"grace_window_seconds": -10}}
            })
        assert "grace_window_seconds" in str(exc_info.value)

    def test_suppressions_grace_days_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"suppressions": {"grace_days": -1}}
            })
        assert "grace_days" in str(exc_info.value)

    def test_issue_review_passes_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"issue_review": {"passes": -1}}
            })
        assert "passes" in str(exc_info.value)

    def test_issue_review_stale_after_days_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"issue_review": {"stale_after_days": -1}}
            })
        assert "stale_after_days" in str(exc_info.value)

    def test_retries_per_state_machine_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"retries": {"per_state_machine": -1}}
            })
        assert "per_state_machine" in str(exc_info.value)

    def test_retries_per_agent_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"retries": {"per_agent": -1}}
            })
        assert "per_agent" in str(exc_info.value)

    def test_token_alert_threshold_negative_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"token_alert_threshold": -1}
            })
        assert "token_alert_threshold" in str(exc_info.value)


class TestEnumsRaiseLoudlyOnUnknownValue:
    """Enums match the documented set; unknown enum values raise."""

    def test_escalation_channel_unknown_value_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"escalation": {"channel": "silack"}}
            })
        msg = str(exc_info.value)
        assert "channel" in msg
        assert "silack" in msg
        # Mentions allowed values
        assert "file" in msg or "slack" in msg or "github" in msg

    def test_issue_review_require_for_coach_unknown_value_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"issue_review": {"require_for_coach": "maybe"}}
            })
        msg = str(exc_info.value)
        assert "require_for_coach" in msg
        assert "maybe" in msg

    def test_review_phase_unknown_value_raises(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"review": {"phases": ["mauve"]}}
            })
        msg = str(exc_info.value)
        assert "phases" in msg
        assert "mauve" in msg


class TestErrorMessagesReferenceSpec:
    """Operators hitting a config error must be able to find the canonical
    schema. Every error message references spec §10."""

    def test_unknown_key_error_cites_spec(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({"coach": {"bogus": 1}})
        assert "§10" in str(exc_info.value)

    def test_type_error_cites_spec(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({"coach": {"default_llm": 42}})
        assert "§10" in str(exc_info.value)

    def test_range_error_cites_spec(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"risk_thresholds": {"green": -1}}
            })
        assert "§10" in str(exc_info.value)

    def test_enum_error_cites_spec(self):
        with pytest.raises(CoachConfigError) as exc_info:
            load_coach_config_from_dict({
                "coach": {"escalation": {"channel": "silack"}}
            })
        assert "§10" in str(exc_info.value)


class TestCoachBlockMustBeMapping:
    """A `coach:` value that isn't a mapping is an obvious operator error
    and must surface loudly rather than silently using defaults."""

    def test_coach_as_list_raises(self):
        with pytest.raises(CoachConfigError):
            load_coach_config_from_dict({"coach": []})

    def test_coach_as_string_raises(self):
        with pytest.raises(CoachConfigError):
            load_coach_config_from_dict({"coach": "enabled"})
