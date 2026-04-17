"""
Platform tests: wagon.schema.json + train.schema.json theme pattern.

Issue: #291 (feat(planner): support custom themes via .atdd/config.yaml)
Phase: RED — these tests FAIL on current main.
Gate: GT-010c

Validates that the planner JSON Schemas relax the hardcoded `enum` on
the `theme` field (wagon) and `themes.items` (train) to an open
kebab-case string pattern `^[a-z][a-z0-9-]*$` (Decision #2: dynamic
enums are impossible in static JSON Schema, so runtime validation
handles theme-map merging and the schema only enforces shape).

URN: test:planner:custom-themes:schema-pattern

Acceptance:
- `wagon.schema.json` `theme` is type=string with pattern, NOT enum.
- `train.schema.json` `themes.items` is type=string with pattern,
  NOT enum.
- A wagon with `theme: "qualification"` passes schema validation.
- A wagon with `theme: "UPPER"` or `theme: "1bad"` still fails (shape).
- The 10 built-in theme names still pass (backward compatible).

Target change (Phase 2 / GREEN):
- `src/atdd/planner/schemas/wagon.schema.json` L43: enum → pattern.
- `src/atdd/planner/schemas/train.schema.json` L47-58: enum → pattern.
"""
import json
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root


REPO_ROOT = find_repo_root()
SCHEMAS_DIR = REPO_ROOT / "src" / "atdd" / "planner" / "schemas"
WAGON_SCHEMA = SCHEMAS_DIR / "wagon.schema.json"
TRAIN_SCHEMA = SCHEMAS_DIR / "train.schema.json"

THEME_NAME_PATTERN = r"^[a-z][a-z0-9-]*$"

BUILTIN_THEMES = [
    "commons",
    "mechanic",
    "scenario",
    "match",
    "sensory",
    "player",
    "league",
    "audience",
    "monetization",
    "partnership",
]

CUSTOM_THEMES = ["qualification", "security", "operations", "integration"]


# ---------------------------------------------------------------------------
# Schema loaders
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wagon_schema() -> dict:
    assert WAGON_SCHEMA.exists(), f"wagon.schema.json missing at {WAGON_SCHEMA}"
    with open(WAGON_SCHEMA) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def train_schema() -> dict:
    assert TRAIN_SCHEMA.exists(), f"train.schema.json missing at {TRAIN_SCHEMA}"
    with open(TRAIN_SCHEMA) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def _wagon_validator(wagon_schema):
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft7Validator(wagon_schema)


@pytest.fixture(scope="module")
def _train_validator(train_schema):
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft7Validator(train_schema)


@pytest.fixture
def minimal_wagon() -> dict:
    """A wagon manifest shape that passes all non-theme requirements."""
    return {
        "wagon": "qualify-leads",
        "description": "Qualify inbound leads via chat",
        "subject": "agent:qualifier",
        "context": "inbound chat session",
        "action": "scores lead fit against ICP criteria",
        "goal": "confirm qualified-lead status before handoff",
        "outcome": "lead state advances to QUALIFIED or DROPPED",
        "produce": [],
        "consume": [],
        "wmbt": [],
    }


@pytest.fixture
def minimal_train() -> dict:
    """A train manifest shape that passes all non-theme requirements."""
    return {
        "train_id": "1001-qualify-lead-standard",
        "title": "Qualify Lead Standard",
        "description": "Standard lead qualification flow",
        "themes": ["qualification"],
        "participants": ["qualify-leads"],
        "sequence": [],
    }


# ---------------------------------------------------------------------------
# wagon.schema.json `theme` field shape
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_wagon_theme_is_not_static_enum(wagon_schema):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0001: wagon.theme drops static enum.

    Custom themes from `.atdd/config.yaml` cannot be enumerated in a
    static JSON Schema. The enum must be removed in favor of a pattern.
    """
    theme_prop = wagon_schema["properties"]["theme"]
    assert "enum" not in theme_prop, (
        "wagon.schema.json `theme` still has a static `enum`. "
        "It must be replaced with `pattern: ^[a-z][a-z0-9-]*$` so "
        "custom themes declared in .atdd/config.yaml are accepted."
    )


@pytest.mark.platform
def test_wagon_theme_uses_kebab_case_pattern(wagon_schema):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0002: wagon.theme has kebab-case pattern.
    """
    theme_prop = wagon_schema["properties"]["theme"]
    assert theme_prop.get("type") == "string"
    assert theme_prop.get("pattern") == THEME_NAME_PATTERN, (
        f"wagon.schema.json `theme` pattern must be "
        f"{THEME_NAME_PATTERN!r}, got {theme_prop.get('pattern')!r}"
    )


@pytest.mark.platform
@pytest.mark.parametrize("custom", CUSTOM_THEMES)
def test_wagon_accepts_custom_theme_name(_wagon_validator, minimal_wagon, custom):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0003: Custom kebab-case theme accepted.

    A wagon declaring `theme: qualification` (semantic domain name from
    consumer repo) must pass schema validation so the consumer can
    complete planner phase without being forced into a game-domain
    default.
    """
    doc = {**minimal_wagon, "theme": custom}
    errors = list(_wagon_validator.iter_errors(doc))
    theme_errors = [e for e in errors if "theme" in "/".join(str(p) for p in e.absolute_path)]
    assert not theme_errors, (
        f"Custom theme '{custom}' should pass wagon schema, got: "
        f"{[e.message for e in theme_errors]}"
    )


@pytest.mark.platform
@pytest.mark.parametrize("builtin", BUILTIN_THEMES)
def test_wagon_still_accepts_builtin_theme(_wagon_validator, minimal_wagon, builtin):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0004: All 10 built-ins still validate.

    Backward compatibility: every built-in theme name from the original
    enum must continue to pass after the switch to pattern.
    """
    doc = {**minimal_wagon, "theme": builtin}
    errors = list(_wagon_validator.iter_errors(doc))
    theme_errors = [e for e in errors if "theme" in "/".join(str(p) for p in e.absolute_path)]
    assert not theme_errors, (
        f"Built-in theme '{builtin}' must still validate, got: "
        f"{[e.message for e in theme_errors]}"
    )


@pytest.mark.platform
@pytest.mark.parametrize(
    "bad",
    ["UPPER", "Qualification", "1bad", "-bad", "with space", "with_under", ""],
)
def test_wagon_rejects_malformed_theme(_wagon_validator, minimal_wagon, bad):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0005: Shape violations rejected.

    Even with the enum removed, malformed strings (UPPER, digit-start,
    spaces, underscores) must fail the kebab-case pattern.
    """
    doc = {**minimal_wagon, "theme": bad}
    errors = list(_wagon_validator.iter_errors(doc))
    theme_errors = [e for e in errors if "theme" in "/".join(str(p) for p in e.absolute_path)]
    assert theme_errors, (
        f"Malformed theme '{bad!r}' must be rejected by kebab-case pattern"
    )


# ---------------------------------------------------------------------------
# train.schema.json `themes.items` field shape
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_train_themes_items_is_not_static_enum(train_schema):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0006: train.themes.items drops static enum.
    """
    themes_prop = train_schema["properties"]["themes"]
    items = themes_prop.get("items", {})
    assert "enum" not in items, (
        "train.schema.json `themes.items` still has a static `enum`. "
        "It must be replaced with pattern-based validation."
    )


@pytest.mark.platform
def test_train_themes_items_uses_kebab_case_pattern(train_schema):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0007: train.themes.items has the pattern.
    """
    items = train_schema["properties"]["themes"]["items"]
    assert items.get("type") == "string"
    assert items.get("pattern") == THEME_NAME_PATTERN, (
        f"train.schema.json `themes.items` pattern must be "
        f"{THEME_NAME_PATTERN!r}, got {items.get('pattern')!r}"
    )


@pytest.mark.platform
@pytest.mark.parametrize("custom", CUSTOM_THEMES)
def test_train_accepts_custom_theme(_train_validator, minimal_train, custom):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0008: Custom theme name validates in train.
    """
    doc = {**minimal_train, "themes": [custom]}
    errors = list(_train_validator.iter_errors(doc))
    theme_errors = [e for e in errors if "themes" in "/".join(str(p) for p in e.absolute_path)]
    assert not theme_errors, (
        f"Custom theme '{custom}' should pass train schema, got: "
        f"{[e.message for e in theme_errors]}"
    )


@pytest.mark.platform
@pytest.mark.parametrize("builtin", BUILTIN_THEMES)
def test_train_still_accepts_builtin_theme(_train_validator, minimal_train, builtin):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0009: Built-in themes still validate in train.
    """
    doc = {**minimal_train, "themes": [builtin]}
    errors = list(_train_validator.iter_errors(doc))
    theme_errors = [e for e in errors if "themes" in "/".join(str(p) for p in e.absolute_path)]
    assert not theme_errors, (
        f"Built-in theme '{builtin}' must still pass, got: "
        f"{[e.message for e in theme_errors]}"
    )


@pytest.mark.platform
@pytest.mark.parametrize("bad", ["UPPER", "1bad", "with space"])
def test_train_rejects_malformed_theme(_train_validator, minimal_train, bad):
    """
    SPEC-PLANNER-SCHEMA-THEMES-0010: Shape violations rejected in train.
    """
    doc = {**minimal_train, "themes": [bad]}
    errors = list(_train_validator.iter_errors(doc))
    theme_errors = [e for e in errors if "themes" in "/".join(str(p) for p in e.absolute_path)]
    assert theme_errors, (
        f"Malformed theme '{bad!r}' must be rejected in train schema"
    )
