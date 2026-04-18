"""
Custom theme map helper (issue #291).

Single source of truth for the digit → theme-name mapping used by
planner validators, coach commands (inventory, registry, sync), and
the init flow. Merges the 10 built-in defaults with the optional
`themes` block in `.atdd/config.yaml` so consumer repos can override
game-domain defaults with names that reflect their own domain.

URN: coach:utils:theme_map

Public surface:
    DEFAULT_THEME_MAP         Dict[str, str]
    get_theme_map(config)     Dict[str, str]
    validate_theme_config     (themes) -> ValidationResult
    Warning                   dataclass: .code, .message
    ValidationResult          dataclass: .errors, .warnings

Conventions: src/atdd/coach/conventions/naming.convention.yaml
             src/atdd/planner/conventions/artifact-naming.convention.yaml
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional


DEFAULT_THEME_MAP: Dict[str, str] = {
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

THEME_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
DIGIT_KEY_PATTERN = re.compile(r"^[0-9]$")


@dataclass(frozen=True)
class Warning:
    """Non-blocking warning emitted by theme config validation."""

    code: str
    message: str


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[Warning] = field(default_factory=list)


def get_theme_map(config: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """
    Merge built-in defaults with optional `themes` overrides from config.

    Args:
        config: Parsed `.atdd/config.yaml` mapping. May be None or lack
            a `themes` key entirely; both cases yield the defaults.

    Returns:
        Dict of digit(str) → theme-name(str). Overrides win; unmapped
        digits retain their built-in value. Integer keys in the config
        are normalized to strings.

    Notes:
        - Pure: does not mutate the input mapping.
        - Invalid override shapes are ignored silently here; call
          `validate_theme_config()` separately to surface errors.
    """
    merged = dict(DEFAULT_THEME_MAP)

    if not config:
        return merged

    overrides = config.get("themes") if isinstance(config, Mapping) else None
    if not overrides:
        return merged

    if not isinstance(overrides, Mapping):
        return merged

    for raw_key, raw_value in overrides.items():
        key = str(raw_key)
        if not DIGIT_KEY_PATTERN.match(key):
            continue
        if not isinstance(raw_value, str) or not THEME_NAME_PATTERN.match(raw_value):
            continue
        merged[key] = raw_value

    return merged


def validate_theme_config(themes: Optional[Mapping[Any, Any]]) -> ValidationResult:
    """
    Validate a raw `themes:` block from `.atdd/config.yaml`.

    Rules:
        - keys must be single digits 0-9
        - values must match ^[a-z][a-z0-9-]*$ and be non-empty strings
        - overriding digit 0 emits non-blocking `W-THEME-001`

    Args:
        themes: The raw mapping under the `themes:` YAML key. May be
            None (treated as empty).

    Returns:
        `ValidationResult` with `.errors` (blocking) and `.warnings`
        (advisory). Callers decide how to surface each.
    """
    result = ValidationResult()

    if themes is None:
        return result

    if not isinstance(themes, Mapping):
        result.errors.append(
            f"themes block must be a mapping, got {type(themes).__name__}"
        )
        return result

    for raw_key, raw_value in themes.items():
        key = str(raw_key) if not isinstance(raw_key, str) else raw_key

        if not DIGIT_KEY_PATTERN.match(key):
            result.errors.append(
                f"themes key must be a single digit 0-9, got {raw_key!r}"
            )
            continue

        if raw_value is None:
            result.errors.append(
                f"themes[{key!r}] is null — theme name is required"
            )
            continue

        if not isinstance(raw_value, str):
            result.errors.append(
                f"themes[{key!r}] must be a string, got "
                f"{type(raw_value).__name__}"
            )
            continue

        if not raw_value:
            result.errors.append(
                f"themes[{key!r}] is empty — theme name is required"
            )
            continue

        if not THEME_NAME_PATTERN.match(raw_value):
            result.errors.append(
                f"themes[{key!r}] = {raw_value!r} does not match kebab-case "
                f"pattern ^[a-z][a-z0-9-]*$"
            )
            continue

        if key == "0":
            result.warnings.append(
                Warning(
                    code="W-THEME-001",
                    message=(
                        "Overriding digit 0 (commons) is not recommended — "
                        "cross-repo tooling assumes `commons` at digit 0."
                    ),
                )
            )

    return result
