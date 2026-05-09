"""
Coach v9 configuration loader (`coach.*` block per spec §10).

Coach reads `.atdd/config.yaml::coach` once at startup. This module
materializes that block as an immutable `CoachConfig` value object and
refuses any deviation from the closed schema (unknown keys, wrong types,
out-of-range numbers, unknown enum values) with loud errors that cite
spec §10.

Why closed-schema:
  Coach config is closed-schema (every valid key is named in spec §10).
  A typo like `risk_threshhold.green` (note doubled-h) must surface at
  load time, not silently inherit the default and surface as wrong-phase
  behavior hours later in a coach run driving multiple parallel issues.

Public API:
  - load_coach_config(repo_root) -> CoachConfig
  - load_coach_config_from_dict(raw) -> CoachConfig
  - CoachConfig (immutable)
  - CoachConfigError
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from atdd.coach.utils.config import load_atdd_config


SPEC_REF = "spec §10"


class CoachConfigError(ValueError):
    """Raised when `.atdd/config.yaml::coach` violates the spec §10 schema."""


# ---------------------------------------------------------------------------
# Nested value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObserverConfig:
    activity_silence_seconds: int = 90
    process_silence_seconds: int = 30
    rules_dir: str = ".atdd/observer/rules"


@dataclass(frozen=True)
class ReviewConfig:
    enabled: bool = True
    phases: List[str] = field(
        default_factory=lambda: ["planned", "red", "green", "smoke"]
    )
    same_model_warning: bool = True
    same_model_allowed: bool = False


@dataclass(frozen=True)
class ValidatorsConfig:
    enabled: bool = True
    grace_window_seconds: int = 30
    selection: str = "default"
    pytest_args: List[str] = field(
        default_factory=lambda: ["-x", "--tb=short"]
    )


@dataclass(frozen=True)
class SuppressionsConfig:
    honor: bool = True
    block_on_stale: bool = True
    grace_days: int = 7


@dataclass(frozen=True)
class RiskThresholds:
    planned: Optional[int] = None
    red: Optional[int] = None
    green: Optional[int] = 10
    smoke: Optional[int] = 15
    refactor: Optional[int] = 5
    complete: Optional[int] = 0


@dataclass(frozen=True)
class JudgeConfig:
    enabled: bool = True
    fail_open: bool = False
    log_full_inputs: bool = False


@dataclass(frozen=True)
class IssueReviewConfig:
    passes: int = 3
    llms: List[str] = field(
        default_factory=lambda: ["claude-haiku", "gpt-5-mini", "gemini-flash"]
    )
    dimensions: List[str] = field(
        default_factory=lambda: [
            "systemic", "ambiguities", "gap", "regression", "comprehensiveness",
        ]
    )
    require_for_coach: str = "warn"
    stale_after_days: int = 14


@dataclass(frozen=True)
class EscalationConfig:
    channel: str = "file"
    slack_webhook: Optional[str] = None
    github_label: str = "coach-escalation"


@dataclass(frozen=True)
class RetriesConfig:
    per_state_machine: int = 3
    per_agent: int = 2


@dataclass(frozen=True)
class PersonaLLM:
    """Persona-to-LLM map. Mapping protocol so consumers can do `cfg.persona_llm["reviewer"]`."""
    planner: str = "claude-code"
    tester: str = "claude-code"
    coder: str = "claude-code"
    reviewer: str = "gpt-5"

    def __getitem__(self, persona: str) -> str:
        if persona not in PERSONA_KEYS:
            raise KeyError(persona)
        return getattr(self, persona)

    def __contains__(self, persona: object) -> bool:
        return persona in PERSONA_KEYS


PERSONA_KEYS: Tuple[str, ...] = ("planner", "tester", "coder", "reviewer")


@dataclass(frozen=True)
class CoachConfig:
    default_llm: str = "claude-code"
    judge_llm: str = "claude-haiku"
    persona_llm: PersonaLLM = field(default_factory=PersonaLLM)
    observer: ObserverConfig = field(default_factory=ObserverConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    validators: ValidatorsConfig = field(default_factory=ValidatorsConfig)
    suppressions: SuppressionsConfig = field(default_factory=SuppressionsConfig)
    risk_thresholds: RiskThresholds = field(default_factory=RiskThresholds)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    issue_review: IssueReviewConfig = field(default_factory=IssueReviewConfig)
    escalation: EscalationConfig = field(default_factory=EscalationConfig)
    retries: RetriesConfig = field(default_factory=RetriesConfig)
    token_alert_threshold: int = 400000


# ---------------------------------------------------------------------------
# Schema (key sets, types, enums, ranges)
# ---------------------------------------------------------------------------


TOP_LEVEL_KEYS: Tuple[str, ...] = (
    "default_llm",
    "judge_llm",
    "persona_llm",
    "observer",
    "review",
    "validators",
    "suppressions",
    "risk_thresholds",
    "judge",
    "issue_review",
    "escalation",
    "retries",
    "token_alert_threshold",
)


RISK_PHASES: Tuple[str, ...] = (
    "planned", "red", "green", "smoke", "refactor", "complete",
)
REVIEW_PHASE_VALUES: Tuple[str, ...] = (
    "init", "planned", "red", "green", "smoke", "refactor", "complete",
)
ESCALATION_CHANNELS: Tuple[str, ...] = ("file", "slack", "github")
REQUIRE_FOR_COACH_VALUES: Tuple[str, ...] = ("warn", "block", "off")


# ---------------------------------------------------------------------------
# Validation primitives
# ---------------------------------------------------------------------------


def _err(path: str, detail: str) -> CoachConfigError:
    return CoachConfigError(
        f"coach config error at `coach.{path}`: {detail}. See {SPEC_REF}."
    )


def _check_unknown_keys(
    raw: Mapping[str, Any], allowed: Sequence[str], section: str
) -> None:
    unknown = [k for k in raw.keys() if k not in allowed]
    if unknown:
        path = f"{section}.{unknown[0]}" if section else unknown[0]
        raise _err(
            path,
            f"unknown key (allowed under `coach.{section}`: {sorted(allowed)})"
            if section
            else f"unknown top-level key (allowed: {sorted(allowed)})",
        )


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _err(path, f"expected mapping, got {_type_name(value)}")
    return value


def _bool(value: Any, path: str) -> bool:
    # bool is a subclass of int in Python, so this guard order matters.
    if not isinstance(value, bool):
        raise _err(path, f"expected bool, got {_type_name(value)}")
    return value


def _int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _err(path, f"expected int, got {_type_name(value)}")
    return value


def _str(value: Any, path: str) -> str:
    if not isinstance(value, str):
        raise _err(path, f"expected string, got {_type_name(value)}")
    return value


def _non_negative_int(value: Any, path: str) -> int:
    n = _int(value, path)
    if n < 0:
        raise _err(path, f"expected non-negative int, got {n}")
    return n


def _optional_non_negative_int(value: Any, path: str) -> Optional[int]:
    if value is None:
        return None
    return _non_negative_int(value, path)


def _list_of_str(value: Any, path: str) -> List[str]:
    if not isinstance(value, list):
        raise _err(path, f"expected list, got {_type_name(value)}")
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise _err(
                f"{path}[{i}]",
                f"expected string element, got {_type_name(item)}",
            )
    return list(value)


def _enum(value: Any, path: str, allowed: Sequence[str]) -> str:
    s = _str(value, path)
    if s not in allowed:
        raise _err(
            path,
            f"unknown value {s!r} (allowed: {list(allowed)})",
        )
    return s


def _list_of_enum(value: Any, path: str, allowed: Sequence[str]) -> List[str]:
    items = _list_of_str(value, path)
    for i, item in enumerate(items):
        if item not in allowed:
            raise _err(
                f"{path}[{i}]",
                f"unknown value {item!r} (allowed: {list(allowed)})",
            )
    return items


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    return type(value).__name__


# ---------------------------------------------------------------------------
# Section parsers
# ---------------------------------------------------------------------------


def _parse_persona_llm(raw: Any) -> PersonaLLM:
    if raw is None:
        return PersonaLLM()
    mapping = _require_mapping(raw, "persona_llm")
    _check_unknown_keys(mapping, PERSONA_KEYS, "persona_llm")
    overrides = {
        key: _str(mapping[key], f"persona_llm.{key}")
        for key in mapping
    }
    return PersonaLLM(**{**PersonaLLM().__dict__, **overrides})


def _parse_observer(raw: Any) -> ObserverConfig:
    if raw is None:
        return ObserverConfig()
    mapping = _require_mapping(raw, "observer")
    allowed = ("activity_silence_seconds", "process_silence_seconds", "rules_dir")
    _check_unknown_keys(mapping, allowed, "observer")
    overrides: Dict[str, Any] = {}
    if "activity_silence_seconds" in mapping:
        overrides["activity_silence_seconds"] = _non_negative_int(
            mapping["activity_silence_seconds"], "observer.activity_silence_seconds"
        )
    if "process_silence_seconds" in mapping:
        overrides["process_silence_seconds"] = _non_negative_int(
            mapping["process_silence_seconds"], "observer.process_silence_seconds"
        )
    if "rules_dir" in mapping:
        overrides["rules_dir"] = _str(mapping["rules_dir"], "observer.rules_dir")
    return ObserverConfig(**{**ObserverConfig().__dict__, **overrides})


def _parse_review(raw: Any) -> ReviewConfig:
    if raw is None:
        return ReviewConfig()
    mapping = _require_mapping(raw, "review")
    allowed = ("enabled", "phases", "same_model_warning", "same_model_allowed")
    _check_unknown_keys(mapping, allowed, "review")
    overrides: Dict[str, Any] = {}
    if "enabled" in mapping:
        overrides["enabled"] = _bool(mapping["enabled"], "review.enabled")
    if "phases" in mapping:
        phases = _list_of_enum(mapping["phases"], "review.phases", REVIEW_PHASE_VALUES)
        overrides["phases"] = phases
    if "same_model_warning" in mapping:
        overrides["same_model_warning"] = _bool(
            mapping["same_model_warning"], "review.same_model_warning"
        )
    if "same_model_allowed" in mapping:
        overrides["same_model_allowed"] = _bool(
            mapping["same_model_allowed"], "review.same_model_allowed"
        )
    return ReviewConfig(**{**ReviewConfig().__dict__, **overrides})


def _parse_validators(raw: Any) -> ValidatorsConfig:
    if raw is None:
        return ValidatorsConfig()
    mapping = _require_mapping(raw, "validators")
    allowed = ("enabled", "grace_window_seconds", "selection", "pytest_args")
    _check_unknown_keys(mapping, allowed, "validators")
    overrides: Dict[str, Any] = {}
    if "enabled" in mapping:
        overrides["enabled"] = _bool(mapping["enabled"], "validators.enabled")
    if "grace_window_seconds" in mapping:
        overrides["grace_window_seconds"] = _non_negative_int(
            mapping["grace_window_seconds"], "validators.grace_window_seconds"
        )
    if "selection" in mapping:
        overrides["selection"] = _str(mapping["selection"], "validators.selection")
    if "pytest_args" in mapping:
        overrides["pytest_args"] = _list_of_str(
            mapping["pytest_args"], "validators.pytest_args"
        )
    return ValidatorsConfig(**{**ValidatorsConfig().__dict__, **overrides})


def _parse_suppressions(raw: Any) -> SuppressionsConfig:
    if raw is None:
        return SuppressionsConfig()
    mapping = _require_mapping(raw, "suppressions")
    allowed = ("honor", "block_on_stale", "grace_days")
    _check_unknown_keys(mapping, allowed, "suppressions")
    overrides: Dict[str, Any] = {}
    if "honor" in mapping:
        overrides["honor"] = _bool(mapping["honor"], "suppressions.honor")
    if "block_on_stale" in mapping:
        overrides["block_on_stale"] = _bool(
            mapping["block_on_stale"], "suppressions.block_on_stale"
        )
    if "grace_days" in mapping:
        overrides["grace_days"] = _non_negative_int(
            mapping["grace_days"], "suppressions.grace_days"
        )
    return SuppressionsConfig(**{**SuppressionsConfig().__dict__, **overrides})


def _parse_risk_thresholds(raw: Any) -> RiskThresholds:
    if raw is None:
        return RiskThresholds()
    mapping = _require_mapping(raw, "risk_thresholds")
    _check_unknown_keys(mapping, RISK_PHASES, "risk_thresholds")
    overrides: Dict[str, Any] = {}
    for phase in mapping:
        overrides[phase] = _optional_non_negative_int(
            mapping[phase], f"risk_thresholds.{phase}"
        )
    return RiskThresholds(**{**RiskThresholds().__dict__, **overrides})


def _parse_judge(raw: Any) -> JudgeConfig:
    if raw is None:
        return JudgeConfig()
    mapping = _require_mapping(raw, "judge")
    allowed = ("enabled", "fail_open", "log_full_inputs")
    _check_unknown_keys(mapping, allowed, "judge")
    overrides: Dict[str, Any] = {}
    if "enabled" in mapping:
        overrides["enabled"] = _bool(mapping["enabled"], "judge.enabled")
    if "fail_open" in mapping:
        overrides["fail_open"] = _bool(mapping["fail_open"], "judge.fail_open")
    if "log_full_inputs" in mapping:
        overrides["log_full_inputs"] = _bool(
            mapping["log_full_inputs"], "judge.log_full_inputs"
        )
    return JudgeConfig(**{**JudgeConfig().__dict__, **overrides})


def _parse_issue_review(raw: Any) -> IssueReviewConfig:
    if raw is None:
        return IssueReviewConfig()
    mapping = _require_mapping(raw, "issue_review")
    allowed = (
        "passes", "llms", "dimensions", "require_for_coach", "stale_after_days",
    )
    _check_unknown_keys(mapping, allowed, "issue_review")
    overrides: Dict[str, Any] = {}
    if "passes" in mapping:
        overrides["passes"] = _non_negative_int(
            mapping["passes"], "issue_review.passes"
        )
    if "llms" in mapping:
        overrides["llms"] = _list_of_str(mapping["llms"], "issue_review.llms")
    if "dimensions" in mapping:
        overrides["dimensions"] = _list_of_str(
            mapping["dimensions"], "issue_review.dimensions"
        )
    if "require_for_coach" in mapping:
        overrides["require_for_coach"] = _enum(
            mapping["require_for_coach"],
            "issue_review.require_for_coach",
            REQUIRE_FOR_COACH_VALUES,
        )
    if "stale_after_days" in mapping:
        overrides["stale_after_days"] = _non_negative_int(
            mapping["stale_after_days"], "issue_review.stale_after_days"
        )
    return IssueReviewConfig(**{**IssueReviewConfig().__dict__, **overrides})


def _parse_escalation(raw: Any) -> EscalationConfig:
    if raw is None:
        return EscalationConfig()
    mapping = _require_mapping(raw, "escalation")
    allowed = ("channel", "slack_webhook", "github_label")
    _check_unknown_keys(mapping, allowed, "escalation")
    overrides: Dict[str, Any] = {}
    if "channel" in mapping:
        overrides["channel"] = _enum(
            mapping["channel"], "escalation.channel", ESCALATION_CHANNELS
        )
    if "slack_webhook" in mapping:
        webhook = mapping["slack_webhook"]
        if webhook is not None and not isinstance(webhook, str):
            raise _err(
                "escalation.slack_webhook",
                f"expected string or null, got {_type_name(webhook)}",
            )
        overrides["slack_webhook"] = webhook
    if "github_label" in mapping:
        overrides["github_label"] = _str(
            mapping["github_label"], "escalation.github_label"
        )
    return EscalationConfig(**{**EscalationConfig().__dict__, **overrides})


def _parse_retries(raw: Any) -> RetriesConfig:
    if raw is None:
        return RetriesConfig()
    mapping = _require_mapping(raw, "retries")
    allowed = ("per_state_machine", "per_agent")
    _check_unknown_keys(mapping, allowed, "retries")
    overrides: Dict[str, Any] = {}
    if "per_state_machine" in mapping:
        overrides["per_state_machine"] = _non_negative_int(
            mapping["per_state_machine"], "retries.per_state_machine"
        )
    if "per_agent" in mapping:
        overrides["per_agent"] = _non_negative_int(
            mapping["per_agent"], "retries.per_agent"
        )
    return RetriesConfig(**{**RetriesConfig().__dict__, **overrides})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_coach_config_from_dict(raw: Optional[Mapping[str, Any]]) -> CoachConfig:
    """
    Parse the `coach.*` block out of a parsed `.atdd/config.yaml` dict.

    Args:
        raw: Top-level dict from `.atdd/config.yaml`. None / missing
             `coach` key returns a CoachConfig populated with defaults.

    Returns:
        Immutable CoachConfig populated per spec §10.

    Raises:
        CoachConfigError: when the coach block contains unknown keys,
            wrong types, out-of-range numbers, or unknown enum values.
            Error messages cite spec §10.
    """
    if raw is None:
        return CoachConfig()
    if not isinstance(raw, Mapping):
        return CoachConfig()
    if "coach" not in raw:
        return CoachConfig()

    coach_block = raw["coach"]
    if coach_block is None:
        return CoachConfig()
    if not isinstance(coach_block, Mapping):
        raise CoachConfigError(
            f"coach config error at `coach`: expected mapping, "
            f"got {_type_name(coach_block)}. See {SPEC_REF}."
        )

    _check_unknown_keys(coach_block, TOP_LEVEL_KEYS, "")

    overrides: Dict[str, Any] = {}
    if "default_llm" in coach_block:
        overrides["default_llm"] = _str(coach_block["default_llm"], "default_llm")
    if "judge_llm" in coach_block:
        overrides["judge_llm"] = _str(coach_block["judge_llm"], "judge_llm")
    if "persona_llm" in coach_block:
        overrides["persona_llm"] = _parse_persona_llm(coach_block["persona_llm"])
    if "observer" in coach_block:
        overrides["observer"] = _parse_observer(coach_block["observer"])
    if "review" in coach_block:
        overrides["review"] = _parse_review(coach_block["review"])
    if "validators" in coach_block:
        overrides["validators"] = _parse_validators(coach_block["validators"])
    if "suppressions" in coach_block:
        overrides["suppressions"] = _parse_suppressions(coach_block["suppressions"])
    if "risk_thresholds" in coach_block:
        overrides["risk_thresholds"] = _parse_risk_thresholds(
            coach_block["risk_thresholds"]
        )
    if "judge" in coach_block:
        overrides["judge"] = _parse_judge(coach_block["judge"])
    if "issue_review" in coach_block:
        overrides["issue_review"] = _parse_issue_review(coach_block["issue_review"])
    if "escalation" in coach_block:
        overrides["escalation"] = _parse_escalation(coach_block["escalation"])
    if "retries" in coach_block:
        overrides["retries"] = _parse_retries(coach_block["retries"])
    if "token_alert_threshold" in coach_block:
        overrides["token_alert_threshold"] = _non_negative_int(
            coach_block["token_alert_threshold"], "token_alert_threshold"
        )

    return CoachConfig(**overrides)


def load_coach_config(repo_root: Path) -> CoachConfig:
    """
    Load and parse the `coach.*` block from `<repo_root>/.atdd/config.yaml`.

    Args:
        repo_root: Repository root path.

    Returns:
        Immutable CoachConfig populated per spec §10. If the config file
        is missing, returns a CoachConfig with all defaults.

    Raises:
        CoachConfigError: when the coach block violates spec §10.
    """
    raw = load_atdd_config(repo_root)
    return load_coach_config_from_dict(raw)
