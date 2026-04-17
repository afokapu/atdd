"""
Platform tests: Custom theme runtime validator.

Issue: #291 (feat(planner): support custom themes via .atdd/config.yaml)
Phase: RED — these tests FAIL on current main.
Gates: GT-010d, GT-025

Validates the runtime theme-config validator that enforces the rules
declared in the Scope section of #291:
- digit keys 0-9 only
- kebab-case names (`^[a-z][a-z0-9-]*$`)
- non-empty names
- emits warning `W-THEME-001` when digit 0 is overridden (Decision #4:
  non-blocking — consumers *may* override `commons` but shouldn't;
  cross-repo tooling assumes commons at digit 0).

URN: test:coach:custom-themes:runtime-validator

Target module (Phase 2 / GREEN): `atdd.coach.utils.theme_map`
- `validate_theme_config(themes: dict) -> ValidationResult`
- ValidationResult has `.errors: list[str]` and `.warnings: list[Warning]`
- Warning is a dataclass/namedtuple with `.code` and `.message`
  fields; `.code == "W-THEME-001"` for the digit-0 override case.
"""
import pytest


# ---------------------------------------------------------------------------
# Module import guard
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_validate_theme_config_is_importable():
    """
    SPEC-COACH-THEMES-VAL-0001: `validate_theme_config` exists and is callable.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    assert callable(validate_theme_config)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_empty_themes_is_valid():
    """
    SPEC-COACH-THEMES-VAL-0002: Empty dict produces no errors/warnings.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({})
    assert list(result.errors) == []
    assert list(result.warnings) == []


@pytest.mark.platform
def test_single_valid_override_produces_no_errors():
    """
    SPEC-COACH-THEMES-VAL-0003: Valid single override passes cleanly.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({"1": "qualification"})
    assert list(result.errors) == []
    assert list(result.warnings) == []


@pytest.mark.platform
def test_pluggy_three_overrides_pass_cleanly():
    """
    SPEC-COACH-THEMES-VAL-0004: Canonical pluggy fixture passes cleanly.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({
        "1": "qualification",
        "2": "security",
        "3": "operations",
    })
    assert list(result.errors) == []
    assert list(result.warnings) == []


# ---------------------------------------------------------------------------
# Error cases — invalid digit keys
# ---------------------------------------------------------------------------


@pytest.mark.platform
@pytest.mark.parametrize(
    "bad_key",
    ["10", "a", "", "01", "1a", "-1", " 1"],
)
def test_non_digit_key_produces_error(bad_key):
    """
    SPEC-COACH-THEMES-VAL-0005: Non-single-digit keys are errors.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({bad_key: "qualification"})
    assert result.errors, (
        f"Expected an error for non-digit key {bad_key!r}"
    )


# ---------------------------------------------------------------------------
# Error cases — invalid theme names
# ---------------------------------------------------------------------------


@pytest.mark.platform
@pytest.mark.parametrize(
    "bad_name",
    [
        "UPPER",
        "Qualification",
        "QUALIFICATION",
        "with space",
        "with_under",
        "1starts-digit",
        "-leading-hyphen",
        "",
    ],
)
def test_non_kebab_case_name_produces_error(bad_name):
    """
    SPEC-COACH-THEMES-VAL-0006: Non-kebab-case names are errors.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({"1": bad_name})
    assert result.errors, (
        f"Expected an error for non-kebab-case name {bad_name!r}"
    )


@pytest.mark.platform
def test_null_value_produces_error():
    """
    SPEC-COACH-THEMES-VAL-0007: `themes: {"1": null}` is an error.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({"1": None})
    assert result.errors, "Null theme name must be an error"


# ---------------------------------------------------------------------------
# W-THEME-001 warning (Decision #4)
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_warning_on_commons_override():
    """
    SPEC-COACH-THEMES-VAL-0008: Overriding digit 0 emits W-THEME-001.

    Decision #4 / Gate GT-025. The warning is NON-BLOCKING (result.errors
    remains empty); cross-repo tooling assumes commons at digit 0 so the
    system flags the override without forbidding it.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({"0": "baseline"})

    assert not result.errors, (
        "Overriding digit 0 must NOT be an error (only a warning)"
    )
    codes = [w.code for w in result.warnings]
    assert "W-THEME-001" in codes, (
        f"Expected warning code W-THEME-001 in warnings, got: {codes}"
    )


@pytest.mark.platform
def test_no_warning_on_non_zero_override():
    """
    SPEC-COACH-THEMES-VAL-0009: Overriding digit 1 does NOT emit W-THEME-001.

    The W-THEME-001 code is digit-0-specific. Overriding any other
    digit (the common case) must not produce this warning.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({"1": "qualification"})
    codes = [w.code for w in result.warnings]
    assert "W-THEME-001" not in codes, (
        f"W-THEME-001 is digit-0-specific; should not fire for digit 1. "
        f"Got warnings: {codes}"
    )


@pytest.mark.platform
def test_warning_message_mentions_commons():
    """
    SPEC-COACH-THEMES-VAL-0010: W-THEME-001 message references `commons`.

    The warning copy must help the operator understand the concern
    (cross-repo tooling assumes `commons` at digit 0).
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({"0": "baseline"})
    msg = next(
        (w.message for w in result.warnings if w.code == "W-THEME-001"),
        "",
    )
    assert "commons" in msg.lower(), (
        f"W-THEME-001 message should mention `commons`, got: {msg!r}"
    )


@pytest.mark.platform
def test_warning_does_not_fire_when_digit_0_absent():
    """
    SPEC-COACH-THEMES-VAL-0011: No digit-0 key = no W-THEME-001.
    """
    from atdd.coach.utils.theme_map import validate_theme_config

    result = validate_theme_config({
        "1": "qualification",
        "2": "security",
        "3": "operations",
    })
    codes = [w.code for w in result.warnings]
    assert "W-THEME-001" not in codes
