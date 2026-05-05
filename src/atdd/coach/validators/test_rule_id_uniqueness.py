# URN: component:govern-lifecycle:enforcement-substrate:test_rule_id_uniqueness:backend:domain
# Runtime: python
# Purpose: Enforce rule-ID grammar + uniqueness across every *.convention.yaml.

"""
Coach gate validator for the rule-ID substrate (issue #340).

What this validator enforces:

1. **Grammar** — Every rule's ``id`` matches ``<DOMAIN>-<TOPIC>-<NNN>`` per
   SPEC-COACH-RULEID-0001. The closed DOMAIN registry is read from
   ``src/atdd/coach/conventions/rule-id.convention.yaml::domains``.
2. **Severity** — Every rule declares an integer ``severity`` in [1, 5] per
   SPEC-COACH-RULEID-0003.
3. **Description** — Every rule has a non-empty ``description`` per
   SPEC-COACH-RULEID-0006.
4. **Uniqueness** — No rule ID is declared in more than one location across
   every ``*.convention.yaml`` in ``src/atdd/`` (and nested subtrees).
5. **Deprecation window** — When ``superseded_by`` is present, both old and
   new IDs must exist; emits a warning, not a failure
   (SPEC-COACH-RULEID-0004).

What this validator does NOT enforce:

- That every emitted ``Violation.rule_id`` has a matching declaration.
  Validators may reference rules that haven't been declared in a convention
  yet (the migration playbook covers staged rollout).
- That conventions without ``rules:`` blocks have been migrated. The
  migration is staged across many issues; the playbook in
  ``rule-id.convention.yaml`` covers the schedule.

Run:
    PYTHONPATH=src python3 -m pytest -q \\
        src/atdd/coach/validators/test_rule_id_uniqueness.py -v
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import (
    _walk_rules,
    extract_rules,
    find_convention_files as _find_convention_files,
)


# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
RULE_ID_CONVENTION = ATDD_PKG_DIR / "coach" / "conventions" / "rule-id.convention.yaml"

# Search roots — every place a *.convention.yaml might live in toolkit-self.
_CONVENTION_ROOTS = [
    ATDD_PKG_DIR,                # installed package (tests load from here)
    find_repo_root() / "src" / "atdd",  # editable install / repo checkout
]


# ---------------------------------------------------------------------------
# Grammar (machine-readable mirror of SPEC-COACH-RULEID-0001)
# ---------------------------------------------------------------------------
RULE_ID_PATTERN = re.compile(
    r"^[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*$"
)


def load_rule_id_convention() -> Dict:
    """Load the rule-id convention. Required — fail loudly if missing."""
    if not RULE_ID_CONVENTION.is_file():
        pytest.fail(
            f"rule-id convention missing at {RULE_ID_CONVENTION}\n"
            f"  This convention defines the closed DOMAIN registry.\n"
            f"  See src/atdd/coach/specs/rule-id.spec.md."
        )
    with open(RULE_ID_CONVENTION) as fh:
        return yaml.safe_load(fh) or {}


def load_allowed_domains() -> set:
    """Read the closed DOMAIN registry from the rule-id convention."""
    data = load_rule_id_convention()
    domains = data.get("domains") or []
    return {str(d) for d in domains}


def load_legacy_patterns() -> List["re.Pattern[str]"]:
    """Compile the ``legacy_grammar:`` regex variants from the rule-id convention.

    Returns an empty list if the section is absent — callers must treat
    legacy acceptance as opt-in. The acceptance contract (issue #389 Phase 1):
    a legacy-shaped ID is accepted *only* when its declaring convention file
    is also listed under ``migration.completed:``.
    """
    data = load_rule_id_convention()
    entries = data.get("legacy_grammar") or []
    compiled: List[re.Pattern[str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pattern = entry.get("pattern")
        if isinstance(pattern, str) and pattern:
            compiled.append(re.compile(pattern))
    return compiled


# ---------------------------------------------------------------------------
# Convention discovery
# ---------------------------------------------------------------------------
def find_convention_files() -> List[Path]:
    """Walk this validator's search roots for ``*.convention.yaml`` files.

    Thin wrapper over :func:`atdd.coach.utils.rule_binding.find_convention_files`
    that pins the toolkit-self search roots used by the uniqueness validator.
    """
    return _find_convention_files(_CONVENTION_ROOTS)


def load_migrated_files() -> List[Path]:
    """Resolve ``migration.completed:`` from the rule-id convention to absolute paths.

    Files NOT in this list are exempt from strict grammar enforcement — they
    pre-date the rule-ID substrate and are scheduled for retrofit per the
    migration playbook in rule-id.convention.yaml. Adding a file to
    ``completed:`` opts it into strict validation.
    """
    data = load_rule_id_convention()
    completed = (data.get("migration") or {}).get("completed") or []

    repo_root = find_repo_root()
    resolved: List[Path] = []
    for rel in completed:
        # Migration paths are written as `src/atdd/<rest>`. Resolve against:
        #   1. consumer / toolkit-self repo root (editable install / checkout)
        #   2. installed package dir, stripping the `src/atdd/` prefix so paths
        #      land at e.g. `<site-packages>/atdd/<rest>` for pip installs
        #   3. legacy two-up-from-pkg fallback for older repo layouts
        pkg_relative = (
            rel[len("src/atdd/"):] if rel.startswith("src/atdd/") else rel
        )
        candidates = [
            repo_root / rel,
            ATDD_PKG_DIR / pkg_relative,
            ATDD_PKG_DIR.parent.parent / rel,
        ]
        for cand in candidates:
            if cand.is_file():
                resolved.append(cand.resolve())
                break
    return resolved


# Rule extraction lives in atdd.coach.utils.rule_binding so bind_rule and
# this validator share one walker implementation (issue #388).


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------
def validate_grammar(
    rule_id: str,
    allowed_domains: set,
    legacy_patterns: Optional[List["re.Pattern[str]"]] = None,
) -> Optional[str]:
    """Return error message when *rule_id* fails the grammar; None when OK.

    When ``legacy_patterns`` is supplied, an ID matching any of those patterns
    bypasses the canonical grammar/domain/suffix checks. Callers must only
    pass legacy patterns when validating IDs from a file listed under
    ``migration.completed:`` (issue #389 Phase 1).
    """
    if not isinstance(rule_id, str):
        return f"id must be a string, got {type(rule_id).__name__}"
    if legacy_patterns:
        for pat in legacy_patterns:
            if pat.match(rule_id):
                return None
    if not RULE_ID_PATTERN.match(rule_id):
        return (
            f"id {rule_id!r} does not match canonical namespaced grammar "
            f"<archetype>.<convention_short_name>.<rule_name> (lowercase, "
            f"dot-separated, hyphenated segments)"
        )
    # Canonical archetype must be one of the closed set (issue #399).
    archetype = rule_id.split(".", 1)[0]
    canonical_archetypes = {"coder", "coach", "tester", "planner", "repo"}
    if archetype not in canonical_archetypes:
        return (
            f"id {rule_id!r} uses archetype {archetype!r} which is not in the "
            f"closed registry {sorted(canonical_archetypes)!r}."
        )
    return None


def validate_severity(rule: Dict) -> Optional[str]:
    sev = rule.get("severity")
    if isinstance(sev, bool) or not isinstance(sev, int):
        return f"severity must be int in [1, 5], got {sev!r}"
    if not (1 <= sev <= 5):
        return f"severity must be in [1, 5], got {sev}"
    return None


def validate_description(rule: Dict) -> Optional[str]:
    desc = rule.get("description")
    if not isinstance(desc, str) or not desc.strip():
        return "description must be a non-empty string"
    return None


# ===========================================================================
# Tests
# ===========================================================================

@pytest.mark.coach
def test_rule_id_grammar_and_required_fields():
    """Every structured rule in a *migrated* convention has valid id, severity, description.

    SPEC-COACH-RULEID-0001 (grammar), 0003 (severity), 0006 (per-rule shape).

    Conventions not yet listed under
    ``rule-id.convention.yaml::migration.completed`` are exempt — they pre-date
    the rule-ID substrate and use the legacy prose-rules format. Adding a
    convention to ``completed:`` opts it into strict validation per the
    migration playbook (Phase 5 of issue #340).
    """
    allowed_domains = load_allowed_domains()
    assert allowed_domains, "rule-id convention has no domains: registry"

    migrated = set(load_migrated_files())
    assert migrated, (
        "no migrated convention files declared in "
        "rule-id.convention.yaml::migration.completed"
    )

    legacy_patterns = load_legacy_patterns()

    errors: List[str] = []
    for file_path in find_convention_files():
        if file_path.resolve() not in migrated:
            continue  # legacy convention — out of scope until migrated.

        for _, yaml_path, rule in extract_rules(file_path):
            loc = f"{file_path.name}:{'.'.join(yaml_path[:-1])}[{yaml_path[-1]}]"

            grammar_err = validate_grammar(
                rule.get("id", ""), allowed_domains, legacy_patterns=legacy_patterns
            )
            if grammar_err:
                errors.append(f"{loc}: {grammar_err}")

            sev_err = validate_severity(rule)
            if sev_err:
                errors.append(f"{loc}: {sev_err}")

            desc_err = validate_description(rule)
            if desc_err:
                errors.append(f"{loc}: {desc_err}")

    if errors:
        pytest.fail(
            f"\n\nFound {len(errors)} rule-ID validation error(s) in migrated conventions:\n\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


@pytest.mark.coach
def test_rule_id_uniqueness():
    """No rule ID is declared in more than one place.

    SPEC-COACH-RULEID-0004: stability requires global uniqueness.

    Canonical IDs are checked across every convention. Legacy-shaped IDs
    (issue #389 Phase 1: ``DS-NN``, ``ERR-NN``, ``GP-NN``) are checked only
    when their declaring file is in ``migration.completed:`` — IDs in
    unmigrated files remain out of scope per the migration playbook.

    Other pre-#340 prose IDs (e.g. ``LOG-001``, ``COVERAGE-CODE-4.1``) that
    match neither grammar are still ignored.
    """
    legacy_patterns = load_legacy_patterns()
    migrated = set(load_migrated_files())

    seen: Dict[str, List[str]] = {}
    for file_path in find_convention_files():
        is_migrated = file_path.resolve() in migrated
        for _, yaml_path, rule in extract_rules(file_path):
            rid = rule.get("id")
            if not isinstance(rid, str) or not rid:
                continue
            if RULE_ID_PATTERN.match(rid):
                pass  # canonical — always tracked
            elif is_migrated and any(p.match(rid) for p in legacy_patterns):
                pass  # legacy + migrated — tracked per #389 Phase 1
            else:
                continue
            loc = f"{file_path.name}:{'.'.join(yaml_path[:-1])}[{yaml_path[-1]}]"
            seen.setdefault(rid, []).append(loc)

    duplicates = {rid: locs for rid, locs in seen.items() if len(locs) > 1}
    if duplicates:
        msg_lines = ["\n\nDuplicate rule IDs found:\n"]
        for rid, locs in sorted(duplicates.items()):
            msg_lines.append(f"  {rid}:")
            for loc in locs:
                msg_lines.append(f"    - {loc}")
        msg_lines.append(
            "\nRule IDs are stable forever. To rename, use superseded_by "
            "(SPEC-COACH-RULEID-0004) instead of declaring twice."
        )
        pytest.fail("\n".join(msg_lines))


@pytest.mark.coach
def test_superseded_by_targets_exist():
    """When a rule declares superseded_by, the target ID must also exist.

    SPEC-COACH-RULEID-0004 deprecation window — both old and new live for one
    release. Emit a warning (not failure) so the migration is visible.

    Only conformant rule IDs are checked (legacy IDs are out of scope).
    """
    all_ids: Dict[str, str] = {}  # rule_id -> location
    pairs: List[Tuple[str, str, str]] = []  # (old_id, new_id, location)
    for file_path in find_convention_files():
        for _, yaml_path, rule in extract_rules(file_path):
            rid = rule.get("id")
            if not isinstance(rid, str) or not RULE_ID_PATTERN.match(rid):
                continue
            loc = f"{file_path.name}:{'.'.join(yaml_path[:-1])}[{yaml_path[-1]}]"
            all_ids[rid] = loc
            sup = rule.get("superseded_by")
            if isinstance(sup, str) and sup:
                pairs.append((rid, sup, loc))

    missing = [
        (old, new, loc) for (old, new, loc) in pairs if new not in all_ids
    ]
    if missing:
        msg = "\n".join(
            f"  {loc}: {old} → {new} (target not declared)"
            for (old, new, loc) in missing
        )
        pytest.fail(
            f"\n\n{len(missing)} superseded_by reference(s) point at undeclared rule IDs:\n\n{msg}"
        )

    if pairs:
        warnings.warn(
            f"{len(pairs)} rule(s) in deprecation window (superseded_by present). "
            f"Plan removal in the next toolkit release.",
            UserWarning,
            stacklevel=2,
        )
