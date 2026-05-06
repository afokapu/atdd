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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

from atdd.coach.validators.test_rule_id_uniqueness import find_convention_files


_logger = logging.getLogger(__name__)


class AmbiguousAliasError(LookupError):
    """Raised when a legacy alias collides with another rule's canonical id or alias."""


@dataclass(frozen=True)
class RuleMetadata:
    """Normalized metadata for one declared rule.

    Attributes:
        rule_id: Canonical namespaced identifier
            (``<archetype>.<convention>.<rule>``).
        convention_path: Absolute path to the ``*.convention.yaml`` that
            declared the rule.
        severity: Integer severity 1..5 (per SPEC-COACH-RULEID-0003) when
            present. Some legacy rules use string severities (``"error"``);
            those are preserved as-is.
        description: One-line human-readable rule statement (may be empty
            for legacy rules).
        disposition: Per-rule CI policy (issue #395). One of
            ``"strict"``, ``"suppress-and-clean"``, ``"advisory"``,
            ``"documentation-only"``, or ``None`` when the convention has
            not been migrated yet.
        suppression_deadline: Optional default ``UNTIL=`` for
            suppress-and-clean rules (``YYYY-MM-DD``).
        recipe: Optional pointer to a peer ``*.recipe.yaml`` file
            (without the ``.recipe.yaml`` suffix).
        introduced_in: Optional toolkit version that first published this rule.
        validator: Bidirectional back-reference of form
            ``<module_basename>::<function_name>``, or ``None`` (issue #399).
        fix_hint: Canonical remediation guidance (issue #399), or ``None``.
        aliases: Legacy ids (typically flat-grammar) this canonical rule
            supersedes (issue #399).
        signal_metric: Substrate field (issue #407, spec v12 §4.1). Name of
            the metric the rule's enforcement consumes; the metric runner
            (issue #412) iterates the registry on this field. ``None`` for
            harness-only or non-substrate rules.
        signal_threshold: Substrate field (issue #407). Threshold scalar
            (``int`` / ``float`` / ``bool``) the metric is judged against;
            type is preserved verbatim from the YAML source so the metric
            module's ``passes(value, threshold)`` call sees what the author
            wrote. ``None`` when not set.
    """

    rule_id: str
    convention_path: Path
    severity: object = None
    description: str = ""
    disposition: Optional[str] = None
    suppression_deadline: Optional[str] = None
    recipe: Optional[str] = None
    introduced_in: Optional[str] = None
    validator: Optional[str] = None
    fix_hint: Optional[str] = None
    aliases: Tuple[str, ...] = ()
    signal_metric: Optional[str] = None
    signal_threshold: object = None


def _build_metadata(rule_id: str, raw: Dict, path: Path) -> RuleMetadata:
    aliases_raw = raw.get("aliases")
    if isinstance(aliases_raw, list):
        aliases = tuple(a for a in aliases_raw if isinstance(a, str) and a)
    else:
        aliases = ()
    signal_raw = raw.get("signal")
    signal_metric: Optional[str] = None
    signal_threshold: object = None
    if isinstance(signal_raw, dict):
        sm = signal_raw.get("metric")
        if isinstance(sm, str) and sm:
            signal_metric = sm
        if "threshold" in signal_raw:
            signal_threshold = signal_raw["threshold"]
    else:
        sm = raw.get("signal_metric")
        if isinstance(sm, str) and sm:
            signal_metric = sm
        if "signal_threshold" in raw:
            signal_threshold = raw["signal_threshold"]
    return RuleMetadata(
        rule_id=rule_id,
        convention_path=path,
        severity=raw.get("severity"),
        description=str(raw.get("description") or ""),
        disposition=(
            raw.get("disposition")
            if isinstance(raw.get("disposition"), str)
            else None
        ),
        suppression_deadline=(
            raw.get("suppression_deadline")
            if isinstance(raw.get("suppression_deadline"), str)
            else None
        ),
        recipe=raw.get("recipe") if isinstance(raw.get("recipe"), str) else None,
        introduced_in=(
            raw.get("introduced_in")
            if isinstance(raw.get("introduced_in"), str)
            else None
        ),
        validator=(
            raw.get("validator")
            if isinstance(raw.get("validator"), str) and raw.get("validator")
            else None
        ),
        fix_hint=(
            raw.get("fix_hint")
            if isinstance(raw.get("fix_hint"), str) and raw.get("fix_hint")
            else None
        ),
        aliases=aliases,
        signal_metric=signal_metric,
        signal_threshold=signal_threshold,
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
            _logger.debug(
                "rule_id_registry: skipped %d entries in %s (shape C — no id field)",
                skipped, file_path,
                extra={
                    "skipped_count": skipped,
                    "convention_path": str(file_path),
                    "shape": "C",
                },
            )


_NAMESPACED_RE = __import__("re").compile(
    r"^[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*$"
)


def _looks_like_rule_id(s: str) -> bool:
    """Cheap heuristic: matches namespaced (``coder.x.y``) or legacy flat ids."""
    if not s:
        return False
    if _NAMESPACED_RE.match(s):
        return True
    # Legacy flat: uppercase + hyphenated, never snake_case.
    return s == s.upper() and "-" in s and "_" not in s


def _load_yaml(path: Path):
    try:
        with open(path) as fh:
            return yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        _logger.debug(
            "rule_id_registry: skipping malformed YAML %s: %s",
            path, exc,
            extra={"convention_path": str(path), "error_type": type(exc).__name__},
        )
        return None


def build_registry(
    roots: Optional[Sequence[Path]] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, RuleMetadata]:
    """Build the ``{rule_id: RuleMetadata}`` index.

    Args:
        roots: Optional explicit search roots for ``*.convention.yaml`` files.
            When omitted, uses the toolkit-wide convention discovery from
            ``test_rule_id_uniqueness.find_convention_files``.
        repo_root: Optional consumer repo root to walk for ``plan/`` repo
            rules (substrate spec v12 §4.2). When ``roots`` is the default
            and ``repo_root`` is omitted, the live consumer repo is auto-
            detected via ``find_repo_root()``. Pass ``repo_root=None``
            together with explicit ``roots`` (test mode) to skip the repo
            walk and stay hermetic.

    Returns:
        Dict keyed by rule_id (canonical AND aliases). First occurrence wins
        on cross-file duplication for canonical ids (uniqueness is enforced
        by ``test_rule_id_uniqueness.py``). Alias collisions with another
        canonical id or another rule's alias raise ``AmbiguousAliasError``
        at registry-build time (issue #399).

        Repo-derived rules (acceptance / security URNs) are merged in via
        ``rule_binding.find_repo_rules``; their ``description`` / ``fix_hint``
        flow through the disposition-gate failure formatter so spec §6
        sample blocks render with the same enrichment as toolkit rules.
    """
    if roots is None:
        files: List[Path] = find_convention_files()
        explicit_roots = False
    else:
        files = []
        for root in roots:
            if not Path(root).is_dir():
                continue
            files.extend(sorted(Path(root).rglob("*.convention.yaml")))
        explicit_roots = True

    registry: Dict[str, RuleMetadata] = {}
    canonical_ids: set = set()
    alias_to_canonical: Dict[str, str] = {}

    for path in files:
        if "__pycache__" in path.parts:
            continue
        data = _load_yaml(path)
        if data is None:
            continue
        for rule_id, raw in _walk_node(data, path):
            if rule_id in registry:
                continue
            meta = _build_metadata(rule_id, raw, path)
            registry[rule_id] = meta
            canonical_ids.add(rule_id)

            for alias in meta.aliases:
                if alias in canonical_ids and alias != rule_id:
                    raise AmbiguousAliasError(
                        f"alias {alias!r} on rule {rule_id!r} collides with another "
                        f"rule's canonical id (declared in "
                        f"{registry[alias].convention_path}). "
                        f"Aliases must be unique across the registry."
                    )
                if alias in alias_to_canonical and alias_to_canonical[alias] != rule_id:
                    raise AmbiguousAliasError(
                        f"alias {alias!r} is claimed by both {rule_id!r} and "
                        f"{alias_to_canonical[alias]!r}. Aliases must point at "
                        f"a single canonical rule."
                    )
                alias_to_canonical[alias] = rule_id
                if alias != rule_id:
                    registry.setdefault(alias, meta)

    _merge_repo_rules(registry, repo_root, explicit_roots)
    return registry


def _merge_repo_rules(
    registry: Dict[str, RuleMetadata],
    repo_root: Optional[Path],
    explicit_roots: bool,
) -> None:
    """Merge substrate repo-rule walker output into the registry.

    Walks ``<repo>/plan/`` via ``rule_binding.find_repo_rules`` and converts
    each repo-scoped ``RuleMetadata`` (from ``rule_binding``) into an
    ``rule_id_registry.RuleMetadata`` view. The disposition-gate failure
    formatter consumes ``description`` and ``fix_hint`` from this registry,
    so populating them here is what makes spec v12 §6 sample blocks render
    for repo rules. First-occurrence-wins matches the toolkit-rule path.
    """
    target: Optional[Path]
    if repo_root is not None:
        target = Path(repo_root)
    elif explicit_roots:
        return
    else:
        try:
            from atdd.coach.utils.repo import find_repo_root
        except ImportError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
            # Toolkit packaging shipped without repo-detection — extremely
            # unusual, but the registry must still load convention rules so
            # toolkit-only validators continue to work. Log + skip.
            _logger.debug(
                "rule_id_registry: repo module unavailable, skipping repo walk: %s",
                exc,
                extra={"error_type": type(exc).__name__},
            )
            return
        try:
            target = find_repo_root()
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
            _logger.debug(
                "rule_id_registry: find_repo_root failed, skipping repo walk: %s",
                exc,
                extra={"error_type": type(exc).__name__},
            )
            return
    if target is None or not Path(target).is_dir():
        return

    try:
        from atdd.coach.utils.rule_binding import find_repo_rules
    except ImportError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "rule_id_registry: rule_binding module unavailable, skipping repo walk: %s",
            exc,
            extra={"error_type": type(exc).__name__},
        )
        return

    try:
        repo_rules = find_repo_rules(target)
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "rule_id_registry: skipping repo-rule walk under %s: %s",
            target, exc,
            extra={"repo_root": str(target), "error_type": type(exc).__name__},
        )
        return

    for src_path, repo_meta in repo_rules:
        if repo_meta.rule_id in registry:
            continue
        registry[repo_meta.rule_id] = RuleMetadata(
            rule_id=repo_meta.rule_id,
            convention_path=Path(src_path),
            severity=repo_meta.severity,
            description=repo_meta.description or "",
            disposition=repo_meta.disposition,
            suppression_deadline=None,
            recipe=repo_meta.recipe,
            introduced_in=repo_meta.introduced_in,
            validator=repo_meta.validator,
            fix_hint=repo_meta.fix_hint,
            aliases=repo_meta.aliases,
            signal_metric=repo_meta.signal_metric,
            signal_threshold=repo_meta.signal_threshold,
        )


__all__ = ["AmbiguousAliasError", "RuleMetadata", "build_registry"]
