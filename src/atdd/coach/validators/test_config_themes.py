"""
Platform tests: `themes` section in `.atdd/config.yaml` schema.

Issue: #291 (feat(planner): support custom themes via .atdd/config.yaml)
Phase: RED — these tests FAIL on current main.
Gate: GT-010b

Validates that `src/atdd/coach/schemas/config.schema.json` declares an
optional `themes` property accepting `{digit(0-9): kebab-case-name}`
mappings, and rejects malformed entries.

URN: test:coach:custom-themes:config-schema

Acceptance:
- Schema has a `themes` property (object, optional).
- Empty `themes: {}` is accepted.
- `themes: {"1": "qualification"}` validates.
- `themes: {"1": "qualification", "2": "security"}` validates.
- Invalid keys (non-digit, multi-char, out of 0-9) are rejected.
- Invalid names (UPPER, spaces, digit-start, empty) are rejected.
- The existing config (no `themes` block) still validates (backward
  compatible).

Target change (Phase 2 / GREEN): add a `themes` property to
`src/atdd/coach/schemas/config.schema.json` with
`propertyNames: {pattern: "^[0-9]$"}` and
`additionalProperties: {type: string, pattern: "^[a-z][a-z0-9-]*$"}`.
"""
import json
from pathlib import Path

import pytest

import atdd


# Anchor schema lookup to the installed atdd package, not the consumer repo
# root. find_repo_root() returns the *consumer* repo (no src/atdd/ inside),
# which broke validate-coach in any pip-installed scenario.
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
CONFIG_SCHEMA_PATH = ATDD_PKG_DIR / "coach" / "schemas" / "config.schema.json"


@pytest.fixture(scope="module")
def config_schema() -> dict:
    """Parsed config.schema.json — fails loudly if missing."""
    assert CONFIG_SCHEMA_PATH.exists(), (
        f"config.schema.json not found at {CONFIG_SCHEMA_PATH}"
    )
    with open(CONFIG_SCHEMA_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def _validator(config_schema):
    """jsonschema Draft7Validator — skip if jsonschema not installed."""
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft7Validator(config_schema)


@pytest.fixture
def minimal_valid_config() -> dict:
    """Minimum required config shape (version + release)."""
    return {
        "version": "1.0",
        "release": {"version_file": "pyproject.toml", "tag_prefix": "v"},
    }


# ---------------------------------------------------------------------------
# Schema presence
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_config_schema_declares_themes_property(config_schema):
    """
    SPEC-COACH-CONFIG-THEMES-0001: `themes` is a declared property.

    The schema must enumerate `themes` under its `properties` block so
    that `additionalProperties: false` at the root does not reject
    consumer configs that set it.
    """
    properties = config_schema.get("properties", {})
    assert "themes" in properties, (
        "config.schema.json is missing the `themes` property. "
        "Add it under .properties so consumer repos can declare "
        "custom theme mappings without tripping additionalProperties."
    )


@pytest.mark.platform
def test_themes_property_is_object_type(config_schema):
    """
    SPEC-COACH-CONFIG-THEMES-0002: `themes` must be typed as object.

    Themes are a dict of digit→name. The JSON Schema type must be
    `object` (not array, string, or open).
    """
    themes = config_schema["properties"]["themes"]
    assert themes.get("type") == "object", (
        f"`themes` property must be type=object, got {themes.get('type')}"
    )


@pytest.mark.platform
def test_themes_is_optional(config_schema):
    """
    SPEC-COACH-CONFIG-THEMES-0003: `themes` is NOT in required[].

    Backward compatibility: existing consumer repos without a `themes`
    block must continue to validate.
    """
    required = config_schema.get("required", [])
    assert "themes" not in required, (
        "`themes` must remain optional so existing repos validate "
        "without change."
    )


# ---------------------------------------------------------------------------
# Valid theme configurations
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_config_without_themes_still_validates(_validator, minimal_valid_config):
    """
    SPEC-COACH-CONFIG-THEMES-0004: No `themes` block = valid.

    The current ATDD repo's own `.atdd/config.yaml` has no `themes`
    block. It must continue to validate after schema extension.
    """
    errors = list(_validator.iter_errors(minimal_valid_config))
    assert errors == [], (
        f"Minimal config should validate, got errors: "
        f"{[e.message for e in errors]}"
    )


@pytest.mark.platform
def test_empty_themes_block_validates(_validator, minimal_valid_config):
    """
    SPEC-COACH-CONFIG-THEMES-0005: `themes: {}` is accepted.

    An empty themes block should validate. It is semantically identical
    to no block at all and is a natural intermediate state during
    `atdd init --themes custom`.
    """
    config = {**minimal_valid_config, "themes": {}}
    errors = list(_validator.iter_errors(config))
    assert errors == [], (
        f"Empty themes block should validate, got: "
        f"{[e.message for e in errors]}"
    )


@pytest.mark.platform
def test_single_theme_override_validates(_validator, minimal_valid_config):
    """
    SPEC-COACH-CONFIG-THEMES-0006: One digit→name mapping validates.
    """
    config = {**minimal_valid_config, "themes": {"1": "qualification"}}
    errors = list(_validator.iter_errors(config))
    assert errors == [], (
        f"`themes: {{\"1\": \"qualification\"}}` should validate, got: "
        f"{[e.message for e in errors]}"
    )


@pytest.mark.platform
def test_pluggy_three_theme_overrides_validates(_validator, minimal_valid_config):
    """
    SPEC-COACH-CONFIG-THEMES-0007: The pluggy fixture config validates.

    The fixture from issue #291 declares exactly three overrides.
    This is the canonical "golden" theme config for SMOKE.
    """
    config = {
        **minimal_valid_config,
        "themes": {
            "1": "qualification",
            "2": "security",
            "3": "operations",
        },
    }
    errors = list(_validator.iter_errors(config))
    assert errors == [], (
        f"pluggy 3-override config should validate, got: "
        f"{[e.message for e in errors]}"
    )


@pytest.mark.platform
def test_all_ten_digits_can_be_overridden(_validator, minimal_valid_config):
    """
    SPEC-COACH-CONFIG-THEMES-0008: Keys 0-9 all accepted.
    """
    config = {
        **minimal_valid_config,
        "themes": {str(d): f"theme-{d}" for d in range(10)},
    }
    errors = list(_validator.iter_errors(config))
    assert errors == [], (
        f"All 10 digits should be valid keys, got: "
        f"{[e.message for e in errors]}"
    )


# ---------------------------------------------------------------------------
# Invalid theme keys
# ---------------------------------------------------------------------------


@pytest.mark.platform
@pytest.mark.parametrize(
    "bad_key,reason",
    [
        ("10", "two-digit key exceeds 0-9 range"),
        ("a", "letters disallowed"),
        ("", "empty key disallowed"),
        ("01", "leading-zero multi-char key disallowed"),
        ("1a", "mixed alphanumeric disallowed"),
    ],
)
def test_invalid_theme_key_is_rejected(
    _validator, minimal_valid_config, bad_key, reason
):
    """
    SPEC-COACH-CONFIG-THEMES-0009: Non-single-digit keys rejected.

    Only single digits 0-9 are valid theme-map positions. Multi-char or
    non-digit keys must fail schema validation (prevents silent
    acceptance of malformed themes blocks).
    """
    config = {**minimal_valid_config, "themes": {bad_key: "qualification"}}
    errors = list(_validator.iter_errors(config))
    assert errors, f"Expected rejection for bad key '{bad_key}' ({reason})"


# ---------------------------------------------------------------------------
# Invalid theme names
# ---------------------------------------------------------------------------


@pytest.mark.platform
@pytest.mark.parametrize(
    "bad_name,reason",
    [
        ("Qualification", "UPPER-case letters disallowed"),
        ("QUALIFICATION", "ALL-CAPS disallowed"),
        ("lead qualification", "spaces disallowed"),
        ("lead_qualification", "underscores disallowed"),
        ("1qualification", "digit-start disallowed"),
        ("-qualification", "hyphen-start disallowed"),
        ("", "empty value disallowed"),
    ],
)
def test_invalid_theme_name_is_rejected(
    _validator, minimal_valid_config, bad_name, reason
):
    """
    SPEC-COACH-CONFIG-THEMES-0010: Non-kebab-case names rejected.

    Pattern: `^[a-z][a-z0-9-]*$`. Matches the URN slug convention used
    everywhere else in ATDD (wagon slugs, wmbt slugs, train slugs).
    """
    config = {**minimal_valid_config, "themes": {"1": bad_name}}
    errors = list(_validator.iter_errors(config))
    assert errors, (
        f"Expected rejection for bad name '{bad_name}' ({reason})"
    )
