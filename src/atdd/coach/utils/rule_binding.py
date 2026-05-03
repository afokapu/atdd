# URN: component:govern-lifecycle:enforcement-substrate:rule_binding:backend:domain
# Runtime: python
# Purpose: Bind rule metadata from convention YAML at module-import time so validators stop redeclaring RULE_SEVERITY/RULE_ID constants.

"""Runtime rule-metadata binding (issue #388).

Validators previously hardcoded their rule's severity and description as
module-level constants alongside the convention's authoritative declaration.
That dual declaration drifts: a convention bump to severity 5 leaves the
validator emitting at severity 4 forever.

``bind_rule(rule_id)`` walks every ``*.convention.yaml`` under the toolkit
search roots, locates the matching ``rules:`` entry, and returns a
``RuleMetadata`` view.  Validators call it once at module-import time:

    _RULE = bind_rule("COACH-SILENT-SWALLOW-001")

If the rule is unregistered or appears in two convention files, the call
raises at import — the failure surfaces immediately rather than later in a
silently mis-routed ``Violation`` emission.

Related substrate:

* ``src/atdd/coach/validators/_violation.py`` — consumes ``fix_hint_ref``.
* ``src/atdd/coach/specs/rule-id.spec.md`` — grammar and lifecycle.
* ``src/atdd/coach/conventions/rule-id.convention.yaml`` — DOMAIN registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class RuleNotInRegistryError(LookupError):
    """Raised when ``bind_rule`` cannot find the rule_id in any convention."""


class AmbiguousRuleError(LookupError):
    """Raised when a rule_id appears in more than one convention file."""


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RuleMetadata:
    """Read-only view of a single rule's authoritative declaration.

    Attributes:
        rule_id: Stable ID matching the grammar in ``rule-id.spec.md``.
        severity: Integer 1-5 from the convention (mirrors
            ``Violation.severity``).
        description: One-line human-readable rule statement.
        recipe: Bare peer-recipe filename (no ``.recipe.yaml`` suffix), or
            ``None`` if the convention has no ``recipe:`` field.
        introduced_in: Toolkit version string that first published the rule,
            or ``None``.
        source_path: Absolute path to the convention file that declared the
            rule.  Used in ``AmbiguousRuleError`` messages.
    """

    rule_id: str
    severity: int
    description: str
    recipe: Optional[str]
    introduced_in: Optional[str]
    source_path: Path

    @property
    def fix_hint_ref(self) -> Optional[str]:
        """Structured pointer for ``Violation.fix_hint_ref``.

        Returns ``"recipe:{recipe}"`` when ``recipe`` is set on the
        convention entry, else ``None``.  The shape matches the format
        documented in ``_violation.py``.
        """
        if self.recipe:
            return f"recipe:{self.recipe}"
        return None


# ---------------------------------------------------------------------------
# Convention search roots
# ---------------------------------------------------------------------------
_ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent


def _default_roots() -> List[Path]:
    """Search roots for ``*.convention.yaml`` files (deduped at walk time)."""
    return [_ATDD_PKG_DIR, find_repo_root() / "src" / "atdd"]


# ---------------------------------------------------------------------------
# Walker (lifted out of test_rule_id_uniqueness.py so both consumers share one)
# ---------------------------------------------------------------------------
def _is_structured_rule(item) -> bool:
    """A structured rule is a dict with an ``id`` field.

    Distinguishes from legacy prose ``rules:`` arrays whose items are bare
    strings.
    """
    return isinstance(item, dict) and "id" in item


def _walk_rules(
    node, path_parts: Tuple[str, ...]
) -> Iterable[Tuple[Tuple[str, ...], Dict]]:
    """Recursively yield ``(yaml_path, rule_dict)`` for every structured rule."""
    if isinstance(node, dict):
        for key, value in node.items():
            new_path = path_parts + (str(key),)
            if key == "rules" and isinstance(value, list):
                for idx, item in enumerate(value):
                    if _is_structured_rule(item):
                        yield (new_path + (str(idx),), item)
            else:
                yield from _walk_rules(value, new_path)
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            yield from _walk_rules(item, path_parts + (str(idx),))


def extract_rules(
    file_path: Path,
) -> List[Tuple[Path, Tuple[str, ...], Dict]]:
    """Return ``(file, yaml_path, rule_dict)`` for every structured rule in *file_path*."""
    try:
        with open(file_path) as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return []
    if data is None:
        return []
    return [(file_path, p, r) for (p, r) in _walk_rules(data, ())]


def _find_convention_files(roots: Iterable[Path]) -> List[Path]:
    """Walk *roots* for ``*.convention.yaml`` files (deduped by resolved path)."""
    seen: Dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.convention.yaml"):
            if "__pycache__" in path.parts:
                continue
            seen[str(path.resolve())] = path
    return sorted(seen.values())


# ---------------------------------------------------------------------------
# Registry cache
# ---------------------------------------------------------------------------
# rule_id -> [RuleMetadata, ...] (length > 1 means ambiguous)
_REGISTRY_CACHE: Optional[Dict[str, List[RuleMetadata]]] = None
_OVERRIDE_ROOTS: Optional[List[Path]] = None


def clear_cache(*, override_roots: Optional[Iterable[Path]] = None) -> None:
    """Drop the cached registry.

    Test-only hook.  Pass ``override_roots=[...]`` to seed the next
    ``bind_rule`` call against fixture conventions instead of the live
    toolkit tree.  Pass nothing (or ``override_roots=None``) to reset to the
    default search roots.
    """
    global _REGISTRY_CACHE, _OVERRIDE_ROOTS
    _REGISTRY_CACHE = None
    if override_roots is None:
        _OVERRIDE_ROOTS = None
    else:
        _OVERRIDE_ROOTS = [Path(p) for p in override_roots]


def _load_registry() -> Dict[str, List[RuleMetadata]]:
    """Walk every convention file and index rules by ``rule_id``."""
    roots = _OVERRIDE_ROOTS if _OVERRIDE_ROOTS is not None else _default_roots()
    registry: Dict[str, List[RuleMetadata]] = {}
    for file_path in _find_convention_files(roots):
        for _, _, rule in extract_rules(file_path):
            rid = rule.get("id")
            if not isinstance(rid, str) or not rid:
                continue
            severity = rule.get("severity")
            if not isinstance(severity, int) or isinstance(severity, bool):
                continue  # malformed rules are policed by test_rule_id_uniqueness
            description = rule.get("description") or ""
            recipe = rule.get("recipe")
            introduced_in = rule.get("introduced_in")
            meta = RuleMetadata(
                rule_id=rid,
                severity=severity,
                description=description,
                recipe=recipe if isinstance(recipe, str) and recipe else None,
                introduced_in=(
                    introduced_in
                    if isinstance(introduced_in, str) and introduced_in
                    else None
                ),
                source_path=file_path.resolve(),
            )
            registry.setdefault(rid, []).append(meta)
    return registry


def _get_registry() -> Dict[str, List[RuleMetadata]]:
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        _REGISTRY_CACHE = _load_registry()
    return _REGISTRY_CACHE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def bind_rule(rule_id: str) -> RuleMetadata:
    """Return the convention's metadata for *rule_id*.

    Called at validator module-import time so the failure modes are loud:

    * ``RuleNotInRegistryError`` — the ID is not declared in any
      ``*.convention.yaml`` under the toolkit search roots.
    * ``AmbiguousRuleError`` — the ID is declared in two or more files; the
      message lists every ``source_path``.

    The registry is cached at module level; tests reset it via
    ``clear_cache()``.
    """
    registry = _get_registry()
    matches = registry.get(rule_id, [])
    if not matches:
        raise RuleNotInRegistryError(
            f"rule_id {rule_id!r} is not declared in any convention. "
            f"Add it to a *.convention.yaml under src/atdd/, or fix the "
            f"caller's rule_id."
        )
    if len(matches) > 1:
        paths = "\n  - ".join(str(m.source_path) for m in matches)
        raise AmbiguousRuleError(
            f"rule_id {rule_id!r} is declared in {len(matches)} convention files:\n"
            f"  - {paths}\n"
            f"Rule IDs are stable forever — use superseded_by instead of "
            f"redeclaring."
        )
    return matches[0]


__all__ = [
    "AmbiguousRuleError",
    "RuleMetadata",
    "RuleNotInRegistryError",
    "bind_rule",
    "clear_cache",
    "extract_rules",
]
