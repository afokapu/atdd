# Component: component:atdd-plan-core:subjects:SubjectRegistry:backend:domain
"""Subject registry + subject-invariant mechanic (#1421).

``subject:<name>`` is the 1-token root URN family introduced so a typed
``train:<subject>:<slug>`` has a real parent (see ``urn_grammar.yaml``). This
module is the pure, testable mechanic the ``planner.subject.invariants``
validator and ``SubjectResolver`` share — the peer of ``planner/naming.py`` for
the wagon/feature verb-object rule, but *inverted*: a subject is a durable NOUN,
so the leading token must NOT be a verb.

Invariants enforced over ``plan/_subjects.yaml`` and the typed trains that
reference it:

* **durable noun** — kebab-case, not verb-led (inverse of ``is_verb_object``),
  and not a reserved structural token (a theme, an actor, a route/category/owner/
  program keyword),
* **registered** — a subject named by a typed train exists in the registry,
* **unique-by-subject** — no duplicate registry entries; and **unique-by-
  subject+slug** — no two typed trains collapse to the same identity,
* **registered-before-first-train** — the subject is in the registry before any
  train is typed under it.

Cycle-safe, ``verb_lexicon`` discipline: read the registry with plain ``yaml`` +
``@lru_cache`` (the registry is data, keyed off the repo root, not cached
globally so tests over ``tmp_path`` stay hermetic).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from atdd.planner.naming import verb_lexicon

_KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

#: Registry file, relative to the repo/plan root.
SUBJECTS_REL = Path("plan") / "_subjects.yaml"
_TRAINS_DIR_REL = Path("plan") / "_trains"

# Reserved structural tokens a subject must not be. A subject names *what the
# journey is about*; these name the machinery around it. Themes are added
# dynamically from the resolved theme map so a consumer repo's themes are
# reserved too.
_RESERVED_STRUCTURAL = frozenset({
    "route", "category", "owner", "program", "theme", "wagon", "wagons",
    "train", "trains", "user", "system", "actor", "role", "feature",
})

# Legacy typed-train identity: 4-digit prefix + slug (pre-migration).
_LEGACY_TRAIN_RE = re.compile(r"^\d{4}-[a-z0-9][a-z0-9-]*$")


def _reserved_themes(root: Optional[Path]) -> frozenset:
    """Resolved canonical theme names — reserved (a subject is not a theme).

    Falls back to an empty set if the theme taxonomy can't be resolved (e.g. a
    bare ``tmp_path`` with no ``.atdd/config.yaml``); the structural blocklist
    still applies.
    """
    try:
        from atdd.planner.validators._theme_taxonomy import canonical_theme_set
        from atdd.coach.utils.config import load_atdd_config

        cfg = load_atdd_config(Path(root) if root else Path("."))
        return frozenset(canonical_theme_set(cfg))
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-31
        # Pure-mechanic callers (is_durable_noun with no root) and hermetic
        # tmp_path tests get the structural blocklist only.
        return frozenset()


def is_durable_noun(name: str, *, root: Optional[Path] = None) -> Tuple[bool, Optional[str]]:
    """Return ``(ok, reason)`` — is *name* a durable noun fit to be a subject?

    ``reason`` is ``None`` when ok, else a human-readable explanation of the
    first violated clause. When *root* is given, the resolved theme set is also
    reserved; otherwise only the structural blocklist applies.
    """
    name = name or ""
    if not _KEBAB_RE.match(name):
        return False, (
            f"{name!r} is not kebab-case "
            r"(must match ^[a-z][a-z0-9]*(-[a-z0-9]+)*$)"
        )
    if name in _RESERVED_STRUCTURAL:
        return False, (
            f"{name!r} is a reserved structural keyword (route/category/owner/"
            f"actor/…), not the noun object of a change"
        )
    if name in _reserved_themes(root):
        return False, (
            f"{name!r} is a theme, not a subject; a subject is the durable noun "
            f"a train is *about*, orthogonal to its theme"
        )
    tokens = name.split("-")
    if tokens[0] in verb_lexicon():
        return False, (
            f"leading token {tokens[0]!r} of {name!r} is a verb; a subject is a "
            f"durable NOUN object (e.g. 'artifact-identity'), not a verb-led action"
        )
    return True, None


def load_subject_registry(root: Path) -> dict:
    """Return the parsed ``plan/_subjects.yaml`` (``{}`` when absent)."""
    path = Path(root) / SUBJECTS_REL
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def registered_subjects(root: Path) -> frozenset:
    """The set of registered subject names."""
    data = load_subject_registry(root)
    return frozenset(
        e.get("subject")
        for e in (data.get("subjects") or [])
        if isinstance(e, dict) and e.get("subject")
    )


def subject_registry_violations(root: Path) -> List[str]:
    """Registry-level invariants: durable-noun + unique-by-subject + shape."""
    data = load_subject_registry(root)
    entries = data.get("subjects") or []
    violations: List[str] = []
    seen: set = set()
    for e in entries:
        if not isinstance(e, dict) or not e.get("subject"):
            violations.append(f"subject registry entry missing 'subject': {e!r}")
            continue
        name = e["subject"]
        if name in seen:
            violations.append(f"duplicate subject entry {name!r}: subjects must be unique-by-subject")
            continue
        seen.add(name)
        ok, reason = is_durable_noun(name, root=root)
        if not ok:
            violations.append(f"subject {name!r} is not a durable noun: {reason}")
        for field in ("title", "description", "status"):
            if not e.get(field):
                violations.append(f"subject {name!r} missing required field {field!r}")
    return violations


def _iter_typed_trains(root: Path):
    """Yield ``(path, spec)`` for every train file that declares a typed
    identity (``subject:``/``slug:`` fields or a ``train:<subject>:<slug>``
    urn). Legacy ``NNNN-slug`` trains are skipped — retyping them is the
    migration tool's job (#1421 Layer 7)."""
    tdir = Path(root) / _TRAINS_DIR_REL
    if not tdir.exists():
        return
    for path in sorted(tdir.rglob("*.yaml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(spec, dict):
            continue
        tid = str(spec.get("train_id", ""))
        if _LEGACY_TRAIN_RE.match(tid):
            continue  # legacy, pre-migration — out of scope
        if spec.get("subject") or str(spec.get("urn", "")).startswith("train:"):
            yield path, spec


def _train_subject_slug(spec: dict) -> Tuple[Optional[str], Optional[str]]:
    """Extract ``(subject, slug)`` from a typed train spec (explicit fields win,
    else parse the ``train:<subject>:<slug>`` urn)."""
    subject = spec.get("subject")
    slug = spec.get("slug")
    urn = str(spec.get("urn", ""))
    if (not subject or not slug) and urn.startswith("train:"):
        parts = urn.split(":")
        if len(parts) == 3:
            subject = subject or parts[1]
            slug = slug or parts[2]
    return subject, slug


def unregistered_train_subject_violations(root: Path) -> List[str]:
    """registered-before-first-train: every typed train's subject is registered."""
    registered = registered_subjects(root)
    violations: List[str] = []
    for path, spec in _iter_typed_trains(root):
        subject, _ = _train_subject_slug(spec)
        if subject and subject not in registered:
            violations.append(
                f"{path.name}: train subject {subject!r} is not registered in "
                f"plan/_subjects.yaml (registered-before-first-train)"
            )
    return violations


def typed_train_uniqueness_violations(root: Path) -> List[str]:
    """unique-by-subject+slug: no two typed trains share the same identity."""
    seen: dict = {}
    violations: List[str] = []
    for path, spec in _iter_typed_trains(root):
        subject, slug = _train_subject_slug(spec)
        if not subject or not slug:
            continue
        key = (subject, slug)
        if key in seen:
            violations.append(
                f"{path.name}: duplicate typed train identity "
                f"train:{subject}:{slug} (also {seen[key]})"
            )
            continue
        seen[key] = path.name
    return violations
