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
from typing import Dict, Iterable, List, Optional, Tuple

import pytest
import yaml

import atdd
from atdd.coach.utils.repo import find_repo_root


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
RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(-[A-Z0-9]+){2,4}$")


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


# ---------------------------------------------------------------------------
# Convention discovery
# ---------------------------------------------------------------------------
def find_convention_files() -> List[Path]:
    """Walk *_CONVENTION_ROOTS* for ``*.convention.yaml`` files (deduped)."""
    seen: Dict[str, Path] = {}
    for root in _CONVENTION_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.convention.yaml"):
            # Skip __pycache__-adjacent caches and tests fixtures.
            if "__pycache__" in path.parts:
                continue
            # Dedupe by resolved path so the same file installed + checked-out
            # is not validated twice.
            key = str(path.resolve())
            seen[key] = path
    return sorted(seen.values())


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


# ---------------------------------------------------------------------------
# Rule extraction
# ---------------------------------------------------------------------------
def _is_structured_rule(item) -> bool:
    """A structured rule is a dict with an ``id`` field.

    Distinguishes from legacy prose ``rules:`` arrays whose items are bare
    strings (e.g. green.convention.yaml `composition_completeness.rules:`).
    """
    return isinstance(item, dict) and "id" in item


def _walk_rules(node, path_parts: Tuple[str, ...]) -> Iterable[Tuple[Tuple[str, ...], Dict]]:
    """Recursively yield (yaml_path, rule_dict) for every structured rule."""
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


def extract_rules(file_path: Path) -> List[Tuple[Path, Tuple[str, ...], Dict]]:
    """Return (file, yaml_path, rule_dict) for every structured rule in *file_path*."""
    try:
        with open(file_path) as fh:
            data = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return []
    if data is None:
        return []
    return [(file_path, p, r) for (p, r) in _walk_rules(data, ())]


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------
def validate_grammar(rule_id: str, allowed_domains: set) -> Optional[str]:
    """Return error message when *rule_id* fails the grammar; None when OK."""
    if not isinstance(rule_id, str):
        return f"id must be a string, got {type(rule_id).__name__}"
    if not RULE_ID_PATTERN.match(rule_id):
        return (
            f"id {rule_id!r} does not match grammar "
            f"<DOMAIN>-<TOPIC>-<NNN> (uppercase, 3-digit zero-padded suffix)"
        )
    domain = rule_id.split("-", 1)[0]
    # Handle DEAD-CODE which itself contains a hyphen.
    if rule_id.startswith("DEAD-CODE-"):
        domain = "DEAD-CODE"
    if domain not in allowed_domains:
        return (
            f"id {rule_id!r} uses DOMAIN {domain!r} which is not in the closed "
            f"registry. Add it to src/atdd/coach/conventions/rule-id.convention.yaml::domains "
            f"after editing SPEC-COACH-RULEID-0002."
        )
    # NNN suffix must be exactly 3 digits.
    suffix = rule_id.rsplit("-", 1)[-1]
    if not (len(suffix) == 3 and suffix.isdigit()):
        return f"id {rule_id!r} numeric suffix must be 3 zero-padded digits"
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

    errors: List[str] = []
    for file_path in find_convention_files():
        if file_path.resolve() not in migrated:
            continue  # legacy convention — out of scope until migrated.

        for _, yaml_path, rule in extract_rules(file_path):
            loc = f"{file_path.name}:{'.'.join(yaml_path[:-1])}[{yaml_path[-1]}]"

            grammar_err = validate_grammar(rule.get("id", ""), allowed_domains)
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
    """No grammar-conformant rule ID is declared in more than one place.

    SPEC-COACH-RULEID-0004: stability requires global uniqueness.

    Legacy IDs (e.g. ``LOG-001``, ``COVERAGE-CODE-4.1``) that don't match the
    new grammar are ignored — they belong to the pre-#340 prose-rules world
    and the migration playbook covers retrofitting them.
    """
    seen: Dict[str, List[str]] = {}
    for file_path in find_convention_files():
        for _, yaml_path, rule in extract_rules(file_path):
            rid = rule.get("id")
            if not isinstance(rid, str) or not rid:
                continue
            if not RULE_ID_PATTERN.match(rid):
                continue  # legacy ID — out of scope.
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
