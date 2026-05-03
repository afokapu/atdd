# URN: component:govern-lifecycle:enforcement-substrate:rule_id_registry:backend:domain
# Runtime: python
# Purpose: Aggregate every convention's rules: block into a single {rule_id: metadata} index.

"""
Rule-ID registry walker (issue #387, Phase 1).

Reads every ``src/atdd/**/conventions/*.yaml`` and normalizes the three
observed ``rules:`` shapes (see ``src/atdd/coach/conventions/rule-id.convention.yaml``)
into a single ``{rule_id: RuleMetadata}`` index:

  Shape A  rules: [ { id: "GREEN-URN-001", ... }, ... ]              → contributes
  Shape B  rules: { COACH-SILENT-SWALLOW-001: { id: ..., ... } }      → contributes
  Shape C  rules: { worktree_per_issue: { rule, anti_pattern, ... } } → SKIPPED

Mixed-shape files (e.g. ``logging.convention.yaml`` has both A and B) are
merged with last-write-wins; duplicate IDs across files keep the first
occurrence (uniqueness is enforced separately by
``test_rule_id_uniqueness.py``).

Reuses ``find_convention_files`` from ``test_rule_id_uniqueness.py`` so the
discovery surface stays consistent across the two validators.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from atdd.coach.validators.test_rule_id_uniqueness import find_convention_files


_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuleMetadata:
    """Normalized metadata for one declared rule.

    Attributes:
        rule_id: Stable rule identifier (e.g. ``GREEN-URN-001``).
        convention_path: Absolute path to the ``*.convention.yaml`` that
            declared the rule.
        severity: Integer severity 1..5 (per SPEC-COACH-RULEID-0003) when
            present. Some legacy rules use string severities (``"error"``);
            those are preserved as-is.
        description: One-line human-readable rule statement (may be empty
            for legacy rules).
        recipe: Optional pointer to a peer ``*.recipe.yaml`` file
            (without the ``.recipe.yaml`` suffix).
        introduced_in: Optional toolkit version that first published this rule.
    """

    rule_id: str
    convention_path: Path
    severity: object = None
    description: str = ""
    recipe: Optional[str] = None
    introduced_in: Optional[str] = None


def _build_metadata(rule_id: str, raw: Dict, path: Path) -> RuleMetadata:
    return RuleMetadata(
        rule_id=rule_id,
        convention_path=path,
        severity=raw.get("severity"),
        description=str(raw.get("description") or ""),
        recipe=raw.get("recipe") if isinstance(raw.get("recipe"), str) else None,
        introduced_in=(
            raw.get("introduced_in")
            if isinstance(raw.get("introduced_in"), str)
            else None
        ),
    )


def _walk_node(
    node, file_path: Path
) -> Iterable[Tuple[str, Dict]]:
    """Recursively yield ``(rule_id, raw_dict)`` for every shape A or B rule."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "rules":
                yield from _extract_from_rules_block(value, file_path)
            else:
                yield from _walk_node(value, file_path)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_node(item, file_path)


def _extract_from_rules_block(
    value, file_path: Path
) -> Iterable[Tuple[str, Dict]]:
    """Yield ``(rule_id, raw_dict)`` from a single ``rules:`` block.

    Shape A: list of dicts each carrying ``id:``.
    Shape B: dict keyed by rule id (each value is a dict).
    Shape C: dict whose value dicts have no ``id:`` field — skipped with a
    debug log so the operator can see why entries were dropped.
    """
    if isinstance(value, list):
        # Shape A. Each item is a dict with an `id` field. Recurse into the
        # value bodies too, so nested `rules:` (e.g. green.convention.yaml's
        # urn_naming.rules) still contribute when this list is itself nested.
        for item in value:
            if isinstance(item, dict):
                rid = item.get("id")
                if isinstance(rid, str) and rid:
                    yield (rid, item)
                yield from _walk_node(item, file_path)
        return

    if isinstance(value, dict):
        skipped = 0
        for key, body in value.items():
            if not isinstance(body, dict):
                continue
            rid = body.get("id")
            if isinstance(rid, str) and rid:
                # Shape B: keyed mapping, body has explicit `id:`.
                yield (rid, body)
            elif isinstance(key, str) and _looks_like_rule_id(key):
                # Shape B variant: key IS the rule_id, body has no `id:` field.
                yield (key, body)
            else:
                # Shape C: semantic-keyed mapping with no `id:` — skip.
                skipped += 1
            # Recurse so deeply-nested rules: blocks still contribute.
            yield from _walk_node(body, file_path)
        if skipped:
            _LOGGER.debug(
                "rule_id_registry: skipped %d entries in %s (shape C — no id field)",
                skipped, file_path,
            )


def _looks_like_rule_id(s: str) -> bool:
    """Cheap heuristic: rule IDs are uppercase + hyphenated, never snake_case."""
    return bool(s) and s == s.upper() and "-" in s and "_" not in s


def _load_yaml(path: Path):
    try:
        with open(path) as fh:
            return yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        _LOGGER.debug("rule_id_registry: skipping malformed YAML %s: %s", path, exc)
        return None


def build_registry(roots: Optional[Sequence[Path]] = None) -> Dict[str, RuleMetadata]:
    """Build the ``{rule_id: RuleMetadata}`` index.

    Args:
        roots: Optional explicit search roots. When omitted, uses the
            toolkit-wide convention discovery from
            ``test_rule_id_uniqueness.find_convention_files``.

    Returns:
        Dict keyed by rule_id. First occurrence wins on cross-file
        duplication (uniqueness is enforced by
        ``test_rule_id_uniqueness.py``).
    """
    if roots is None:
        files: List[Path] = find_convention_files()
    else:
        files = []
        for root in roots:
            if not Path(root).is_dir():
                continue
            files.extend(sorted(Path(root).rglob("*.convention.yaml")))

    registry: Dict[str, RuleMetadata] = {}
    for path in files:
        if "__pycache__" in path.parts:
            continue
        data = _load_yaml(path)
        if data is None:
            continue
        for rule_id, raw in _walk_node(data, path):
            if rule_id in registry:
                # Cross-file duplicate. Keep the first occurrence; uniqueness
                # is enforced separately, so we don't need to choose here.
                continue
            registry[rule_id] = _build_metadata(rule_id, raw, path)
    return registry


__all__ = ["RuleMetadata", "build_registry"]
