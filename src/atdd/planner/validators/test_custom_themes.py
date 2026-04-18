"""
Platform tests: Custom theme support via `.atdd/config.yaml`.

Issue: #291 (feat(planner): support custom themes via .atdd/config.yaml)
Phase: RED — these tests FAIL on current main.
Gate: GT-010a

Validates that consumer repos can declare custom theme names in
`.atdd/config.yaml` under a `themes:` block, and that the planner's
theme_map resolves digit → theme by merging hardcoded defaults with
user overrides.

URN: test:planner:custom-themes:config-load-merge

Acceptance (from issue body, Phase 1 deliverables):
- `.atdd/config.yaml` with `themes: {"1": "qualification"}` is parsed
  and merged into theme_map.
- A wagon with `theme: "qualification"` passes runtime validation when
  config declares it.
- Train `1001-*` resolves to theme `"qualification"` (not `"mechanic"`)
  when override is active.
- Unmapped digits fall back to built-in defaults.

Target module (Phase 2 / GREEN): `atdd.coach.utils.theme_map`
- `DEFAULT_THEME_MAP`: dict of 10 built-in digit→theme mappings
- `get_theme_map(config: dict) -> dict`: merge helper (overrides win)
"""
import pytest


# ---------------------------------------------------------------------------
# Module import guard — the helper does not yet exist (Phase 2 deliverable).
# ImportError is the expected RED failure until `theme_map.py` is created.
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_theme_map_module_is_importable():
    """
    SPEC-PLANNER-THEMES-0001: `atdd.coach.utils.theme_map` module exists.

    The custom-theme feature promises a single source of truth for the
    digit→theme mapping. The module must be importable; the import itself
    is the smoke test that the helper was created.
    """
    from atdd.coach.utils import theme_map  # noqa: F401


@pytest.mark.platform
def test_default_theme_map_exposes_ten_builtin_themes():
    """
    SPEC-PLANNER-THEMES-0002: DEFAULT_THEME_MAP contains the 10 built-ins.

    Digits 0-9 must map to the canonical ATDD-toolkit built-in theme
    names. Changing these is a breaking (MAJOR) change and is out of
    scope for #291.
    """
    from atdd.coach.utils.theme_map import DEFAULT_THEME_MAP

    expected = {
        "0": "commons",
        "1": "mechanic",
        "2": "scenario",
        "3": "match",
        "4": "sensory",
        "5": "player",
        "6": "league",
        "7": "audience",
        "8": "monetization",
        "9": "partnership",
    }
    assert DEFAULT_THEME_MAP == expected, (
        f"DEFAULT_THEME_MAP drift: got {DEFAULT_THEME_MAP}, "
        f"expected {expected}. The 10 built-ins are a stable contract."
    )


@pytest.mark.platform
def test_get_theme_map_returns_defaults_when_no_config():
    """
    SPEC-PLANNER-THEMES-0003: Empty config yields the default 10 themes.

    Backward compatibility: existing consumer repos with no `themes:`
    block in `.atdd/config.yaml` must continue to receive the original
    10 built-in theme mappings unchanged.
    """
    from atdd.coach.utils.theme_map import get_theme_map

    result = get_theme_map({})

    assert result["0"] == "commons"
    assert result["1"] == "mechanic"
    assert result["9"] == "partnership"
    assert len(result) == 10, (
        f"Expected 10 digit keys in merged map, got {len(result)}"
    )


@pytest.mark.platform
def test_get_theme_map_applies_single_override():
    """
    SPEC-PLANNER-THEMES-0004: Override wins over default for matching digit.

    Consumer declares `themes: {"1": "qualification"}` → digit 1 resolves
    to "qualification" (not the built-in "mechanic"). Unmapped digits
    retain their defaults (Decision #5: unmapped digits fall back).
    """
    from atdd.coach.utils.theme_map import get_theme_map

    config = {"themes": {"1": "qualification"}}
    merged = get_theme_map(config)

    assert merged["1"] == "qualification", (
        f"Override for digit '1' should yield 'qualification', "
        f"got '{merged['1']}'"
    )
    assert merged["0"] == "commons", "Digit 0 unmapped → should fall back"
    assert merged["2"] == "scenario", "Digit 2 unmapped → should fall back"
    assert merged["9"] == "partnership", "Digit 9 unmapped → should fall back"


@pytest.mark.platform
def test_get_theme_map_applies_multiple_overrides():
    """
    SPEC-PLANNER-THEMES-0005: Multiple overrides compose correctly.

    The pluggy B2B-fintech case (issue origin) declares 3 overrides:
    digit 1 → qualification, digit 2 → security, digit 3 → operations.
    All three must land in the merged map; digits 4-9 fall back.
    """
    from atdd.coach.utils.theme_map import get_theme_map

    config = {
        "themes": {
            "1": "qualification",
            "2": "security",
            "3": "operations",
        }
    }
    merged = get_theme_map(config)

    assert merged["1"] == "qualification"
    assert merged["2"] == "security"
    assert merged["3"] == "operations"
    assert merged["0"] == "commons", "Digit 0 untouched → commons"
    assert merged["4"] == "sensory", "Digit 4 untouched → sensory"


@pytest.mark.platform
def test_get_theme_map_accepts_integer_digit_keys():
    """
    SPEC-PLANNER-THEMES-0006: Integer and string digit keys both work.

    YAML parsers may emit integer keys for bare digit tokens. The helper
    must normalize integer keys (1) to string keys ("1") so downstream
    code (which always uses string digits from train_id[0]) sees a
    consistent shape.
    """
    from atdd.coach.utils.theme_map import get_theme_map

    config = {"themes": {1: "qualification", 2: "security"}}
    merged = get_theme_map(config)

    assert merged["1"] == "qualification", (
        "Integer YAML keys must be normalized to string digits"
    )
    assert merged["2"] == "security"


@pytest.mark.platform
def test_get_theme_map_ignores_missing_themes_key():
    """
    SPEC-PLANNER-THEMES-0007: Config without `themes` key = pure defaults.

    A real-world `.atdd/config.yaml` contains `release`, `sync`,
    `github`, etc. The helper must tolerate the absence of the optional
    `themes` key without raising.
    """
    from atdd.coach.utils.theme_map import get_theme_map

    config = {
        "version": "1.0",
        "release": {"version_file": "pyproject.toml", "tag_prefix": "v"},
        "sync": {"agents": ["claude"]},
    }
    merged = get_theme_map(config)

    assert merged["0"] == "commons"
    assert merged["1"] == "mechanic"
    assert len(merged) == 10


@pytest.mark.platform
def test_get_theme_map_tolerates_none_themes_value():
    """
    SPEC-PLANNER-THEMES-0008: `themes: null` (or missing value) = defaults.

    A YAML block with `themes:` and no body parses to None. The helper
    must treat None identically to a missing key.
    """
    from atdd.coach.utils.theme_map import get_theme_map

    merged = get_theme_map({"themes": None})

    assert len(merged) == 10
    assert merged["1"] == "mechanic"


@pytest.mark.platform
def test_get_theme_map_is_pure_does_not_mutate_input():
    """
    SPEC-PLANNER-THEMES-0009: Helper does not mutate caller config.

    `get_theme_map` is called from multiple validators and commands;
    a shared config dict must not accumulate side effects across calls.
    """
    from atdd.coach.utils.theme_map import get_theme_map

    config = {"themes": {"1": "qualification"}}
    original_themes = dict(config["themes"])

    _ = get_theme_map(config)

    assert config["themes"] == original_themes, (
        "Helper must not mutate caller-owned config dict"
    )


@pytest.mark.platform
def test_train_id_resolves_theme_via_merged_map():
    """
    SPEC-PLANNER-THEMES-0010: Train `1001-*` resolves via merged theme_map.

    End-to-end expectation from Phase 1 deliverable: when config declares
    `themes: {"1": "qualification"}`, a train whose ID starts with digit
    1 (e.g. `1001-qualify-lead-standard`) must resolve to theme
    "qualification", not the built-in "mechanic".

    This is the regression-proof check that existing call sites
    (inventory.py L142, registry.py L1016, test_train_validation.py
    L75) are rewired through `get_theme_map`.
    """
    from atdd.coach.utils.theme_map import get_theme_map

    config = {"themes": {"1": "qualification"}}
    theme_map = get_theme_map(config)

    train_id = "1001-qualify-lead-standard"
    first_digit = train_id[0]
    resolved_theme = theme_map[first_digit]

    assert resolved_theme == "qualification", (
        f"Train '{train_id}' under override config should resolve to "
        f"'qualification', got '{resolved_theme}'. This indicates the "
        f"merge is not being applied at the digit→theme resolution site."
    )
