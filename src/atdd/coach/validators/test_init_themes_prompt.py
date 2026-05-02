"""
Platform tests: `atdd init` theme declaration prompt.

Issue: #291 (feat(planner): support custom themes via .atdd/config.yaml)
Phase: RED — these tests FAIL on current main.
Gates: GT-055, GT-070

Validates Decision #7 from the issue: `atdd init` prompts the operator
to declare themes, with copy that is domain-agnostic (never names a
product category such as `game`, `saas`, `fintech`). Non-interactive
flag `--themes {defaults|custom|skip}` routes the same flow for CI.

URN: test:coach:custom-themes:init-prompt

Acceptance:
- Prompt copy contains zero forbidden product-category tokens.
- `--themes defaults` writes no `themes:` block (built-in 10 stay
  active by default).
- `--themes skip` is identical to `defaults` (no `themes:` block
  written) but echoes a reminder on where to configure later.
- `--themes custom` writes a `themes:` block that validates against
  `config.schema.json`.
- Custom flow is seeded by the theme scanner (when detections exist)
  and falls back to a blind prompt otherwise.

Target changes (Phase 2 / GREEN):
- `src/atdd/coach/commands/initializer.py`:
    - module-level constant `THEMES_PROMPT_COPY` (the prompt text).
    - `Initializer._prompt_themes(mode: str, *, repo_root: Path | None = None)
       -> Optional[Dict[str, str]]`.
    - `--themes` CLI flag on `atdd init`.
"""
import inspect
from pathlib import Path

import pytest


FORBIDDEN_PROMPT_TOKENS = [
    "game",
    "gaming",
    "saas",
    "fintech",
    "product category",
]


# ---------------------------------------------------------------------------
# Module surface (Decision #7: symbols the initializer must expose)
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_initializer_exposes_themes_prompt_copy():
    """
    SPEC-COACH-INIT-THEMES-0001: `THEMES_PROMPT_COPY` constant exists.

    The prompt text is extracted as a module-level constant so tests
    can inspect it (GT-070) without invoking I/O.
    """
    from atdd.coach.commands import initializer

    assert hasattr(initializer, "THEMES_PROMPT_COPY"), (
        "Initializer must expose THEMES_PROMPT_COPY for test inspection"
    )
    assert isinstance(initializer.THEMES_PROMPT_COPY, str)
    assert initializer.THEMES_PROMPT_COPY.strip(), (
        "THEMES_PROMPT_COPY must be non-empty"
    )


@pytest.mark.platform
def test_initializer_has_prompt_themes_method():
    """
    SPEC-COACH-INIT-THEMES-0002: `Initializer._prompt_themes` is defined.
    """
    from atdd.coach.commands.initializer import Initializer

    assert hasattr(Initializer, "_prompt_themes"), (
        "Initializer must define `_prompt_themes(mode, *, repo_root=None)`"
    )
    sig = inspect.signature(Initializer._prompt_themes)
    params = set(sig.parameters)
    assert "mode" in params, (
        f"_prompt_themes must accept `mode` parameter, got {params}"
    )


# ---------------------------------------------------------------------------
# Domain-agnostic prompt copy (GT-070)
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_prompt_copy_is_domain_agnostic():
    """
    SPEC-COACH-INIT-THEMES-0003 / GT-070: No forbidden product-category tokens.

    The prompt must not bake in assumptions about who adopts ATDD.
    Forbidden tokens: game, gaming, saas, fintech, product category.
    """
    from atdd.coach.commands.initializer import THEMES_PROMPT_COPY

    lower = THEMES_PROMPT_COPY.lower()
    hits = [t for t in FORBIDDEN_PROMPT_TOKENS if t in lower]
    assert not hits, (
        f"Prompt copy must be domain-agnostic — found forbidden tokens "
        f"{hits} in THEMES_PROMPT_COPY. Decision #7 mandates no product-"
        f"category words."
    )


@pytest.mark.platform
def test_prompt_copy_mentions_three_mode_choices():
    """
    SPEC-COACH-INIT-THEMES-0004: Prompt copy references defaults/custom/skip.

    Operator must be able to read the prompt and understand the three
    flow options (Decision #7).
    """
    from atdd.coach.commands.initializer import THEMES_PROMPT_COPY

    lower = THEMES_PROMPT_COPY.lower()
    for choice in ("defaults", "custom", "skip"):
        assert choice in lower, (
            f"Prompt copy should mention the `{choice}` mode, got: "
            f"{THEMES_PROMPT_COPY!r}"
        )


# ---------------------------------------------------------------------------
# Flag routing (defaults / skip / custom)
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_defaults_mode_returns_none(tmp_path):
    """
    SPEC-COACH-INIT-THEMES-0005: `--themes defaults` yields no block.

    `defaults` means "use built-in 10; write no `themes:` block".
    `_prompt_themes("defaults", ...)` must return None to signal that
    the caller should skip writing the block.
    """
    from atdd.coach.commands.initializer import Initializer

    initializer = Initializer(target_dir=tmp_path)
    result = initializer._prompt_themes("defaults", repo_root=tmp_path)

    assert result is None, (
        f"defaults mode must yield None (no themes block), got {result!r}"
    )


@pytest.mark.platform
def test_skip_mode_returns_none(tmp_path):
    """
    SPEC-COACH-INIT-THEMES-0006: `--themes skip` yields no block.
    """
    from atdd.coach.commands.initializer import Initializer

    initializer = Initializer(target_dir=tmp_path)
    result = initializer._prompt_themes("skip", repo_root=tmp_path)

    assert result is None, (
        f"skip mode must yield None (no themes block), got {result!r}"
    )


@pytest.mark.platform
def test_invalid_mode_raises(tmp_path):
    """
    SPEC-COACH-INIT-THEMES-0007: Unknown mode raises ValueError.

    CI callers supplying `--themes wizard` (typo) must get a clear
    failure, not silent fallback.
    """
    from atdd.coach.commands.initializer import Initializer

    initializer = Initializer(target_dir=tmp_path)
    with pytest.raises(ValueError):
        initializer._prompt_themes("wizard", repo_root=tmp_path)


# ---------------------------------------------------------------------------
# Custom mode: scanner-seeded, writes valid YAML
# ---------------------------------------------------------------------------


@pytest.mark.platform
def test_custom_mode_with_scanner_detections_seeds_mapping(tmp_path):
    """
    SPEC-COACH-INIT-THEMES-0008 / GT-060: Scanner seeds the custom flow.

    When `plan/**/*.yaml` contains `theme: qualification`, invoking
    `--themes custom` (non-interactive) must pre-populate the mapping
    with `qualification` on some digit. This is the primary integration
    point between the scanner and the prompt.
    """
    from atdd.coach.commands.initializer import Initializer

    # Seed a plan/ tree with an existing custom theme value.
    plan_dir = tmp_path / "plan" / "qualify_leads"
    plan_dir.mkdir(parents=True)
    (plan_dir / "_qualify_leads.yaml").write_text(
        "wagon: qualify-leads\n"
        "description: Qualify inbound leads\n"
        "theme: qualification\n"
        "subject: agent:qualifier\n"
        "context: inbound chat\n"
        "action: scores lead\n"
        "goal: qualify lead\n"
        "outcome: lead qualified\n"
        "produce: []\n"
        "consume: []\n"
        "wmbt: []\n"
    )

    initializer = Initializer(target_dir=tmp_path)
    result = initializer._prompt_themes("custom", repo_root=tmp_path)

    assert isinstance(result, dict), (
        f"custom mode must return a dict of digit→name, got {type(result).__name__}"
    )
    assert "qualification" in result.values(), (
        f"Scanner should have seeded 'qualification' into mapping, "
        f"got: {result}"
    )


@pytest.mark.platform
def test_custom_mode_output_validates_against_config_schema(tmp_path):
    """
    SPEC-COACH-INIT-THEMES-0009 / GT-060: Custom output validates.

    The dict returned by `_prompt_themes("custom", ...)` must, when
    written under the `themes:` key of `.atdd/config.yaml`, validate
    against `coach/schemas/config.schema.json`.
    """
    jsonschema = pytest.importorskip("jsonschema")
    import json

    import atdd
    from atdd.coach.commands.initializer import Initializer

    # Seed scanner input so custom mode has something to return.
    plan_dir = tmp_path / "plan" / "secure_ops"
    plan_dir.mkdir(parents=True)
    (plan_dir / "_secure_ops.yaml").write_text(
        "wagon: secure-ops\n"
        "description: Secure operational access\n"
        "theme: security\n"
        "subject: agent:guard\n"
        "context: runtime\n"
        "action: guards access\n"
        "goal: keep access safe\n"
        "outcome: access is safe\n"
        "produce: []\n"
        "consume: []\n"
        "wmbt: []\n"
    )

    initializer = Initializer(target_dir=tmp_path)
    themes = initializer._prompt_themes("custom", repo_root=tmp_path)
    assert isinstance(themes, dict) and themes, "custom mode yielded no mapping"

    # Anchor to the installed atdd package; find_repo_root() points at the
    # consumer repo, which has no src/atdd/ tree.
    pkg_dir = Path(atdd.__file__).resolve().parent
    schema_path = pkg_dir / "coach" / "schemas" / "config.schema.json"
    with open(schema_path) as f:
        schema = json.load(f)
    validator = jsonschema.Draft7Validator(schema)

    config_doc = {
        "version": "1.0",
        "release": {"version_file": "pyproject.toml", "tag_prefix": "v"},
        "themes": themes,
    }
    errors = list(validator.iter_errors(config_doc))
    assert not errors, (
        f"Custom-mode themes block must validate against config.schema.json, "
        f"got: {[e.message for e in errors]}"
    )


@pytest.mark.platform
def test_custom_mode_on_empty_repo_does_not_crash(tmp_path):
    """
    SPEC-COACH-INIT-THEMES-0010: Blind prompt path — empty repo is OK.

    When the scanner returns nothing (greenfield repo), the non-
    interactive custom flow must still complete without raising. It is
    allowed to return an empty dict (caller writes `themes: {}` — valid
    per config.schema.json).
    """
    from atdd.coach.commands.initializer import Initializer

    initializer = Initializer(target_dir=tmp_path)
    result = initializer._prompt_themes("custom", repo_root=tmp_path)

    assert result is None or isinstance(result, dict), (
        f"custom mode on empty repo must return None or dict, got "
        f"{type(result).__name__}"
    )
