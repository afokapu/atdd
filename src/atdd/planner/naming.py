# Component: component:atdd-plan-core:naming:VerbObjectRule:backend:domain
"""Foundational verb-object naming rule for planner artifacts (#1276).

``wagon`` and ``feature`` slugs are documented as verb-object in
``wagon.convention.yaml`` / ``feature.convention.yaml`` but, before #1276, this
was prose "preference" with no enforcement. This module is the pure, testable
mechanic both the ``atdd validate planner`` validators and the ``atdd plan``
Confirm gate use.

Mechanic (pragmatic, not NLP):
  1. slug is kebab-case ``^[a-z][a-z0-9]*(-[a-z0-9]+)*$``;
  2. slug has >= 2 tokens (a verb and an object);
  3. the leading token is a verb in the convention **verb lexicon**
     (``feature.convention.yaml`` ``artifact_seeds.verb_selection``: the union of
     the ``by_artifact_type`` suggestion verbs and the explicit
     ``lexicon.additional_verbs`` allowlist);
  4. no token is a connective (``and``/``or``/``to``/...): a verb-object name is a
     verb plus a noun object, not a phrase.

A slug listed explicitly in the convention's
``verb_object_enforcement.brand_exceptions`` (per artifact) is allowed to bypass
the rule — brand/proper-noun exceptions must be *explicit in the convention*,
never implicit.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

import yaml

_CONV_DIR = Path(__file__).resolve().parent / "conventions"

_KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# Connectives forbidden in a verb-object slug — their presence signals a phrase
# (``route-to-mode``, ``respond-and-preview``) rather than verb + noun object.
_CONNECTIVES = frozenset({
    "and", "or", "to", "for", "of", "with", "the", "a", "an",
    "in", "on", "by", "via", "from", "at", "as", "into", "onto",
})

_CONVENTION_FILES = {
    "wagon": "wagon.convention.yaml",
    "feature": "feature.convention.yaml",
}


def _load(name: str) -> dict:
    path = _CONV_DIR / name
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


@lru_cache(maxsize=1)
def verb_lexicon() -> frozenset:
    """The canonical allowed-leading-verb set.

    Union of the ``by_artifact_type`` suggestion verbs (the historical
    ``verb_selection`` table) and the explicit ``lexicon.additional_verbs``
    allowlist — so the rule has a complete basis instead of the 21-verb
    suggestion table, which rejects even the convention's own examples (#1276)."""
    vs = _load("feature.convention.yaml").get("artifact_seeds", {}).get("verb_selection", {})
    verbs: set = set()
    for bucket in (vs.get("by_artifact_type") or {}).values():
        verbs.update((bucket or {}).get("verbs") or [])
    verbs.update((vs.get("lexicon") or {}).get("additional_verbs") or [])
    return frozenset(verbs)


@lru_cache(maxsize=4)
def brand_exceptions(artifact: str) -> frozenset:
    """Explicit brand/proper-noun slugs allowed to bypass verb-object, read from
    the artifact's convention ``verb_object_enforcement.brand_exceptions``."""
    fname = _CONVENTION_FILES.get(artifact)
    if not fname:
        return frozenset()
    block = _load(fname).get("verb_object_enforcement") or {}
    return frozenset(block.get("brand_exceptions") or [])


def is_verb_object(slug: str, *, artifact: str = "wagon") -> Tuple[bool, Optional[str]]:
    """Return ``(ok, reason)``. ``reason`` is ``None`` when ``ok`` is True, else a
    human-readable explanation of the first violated clause."""
    slug = slug or ""
    if slug in brand_exceptions(artifact):
        return True, None
    if not _KEBAB_RE.match(slug):
        return False, (
            f"{slug!r} is not kebab-case "
            r"(must match ^[a-z][a-z0-9]*(-[a-z0-9]+)*$)"
        )
    tokens = slug.split("-")
    if len(tokens) < 2:
        return False, (
            f"{slug!r} is a single token; a verb-object name needs a verb and an object "
            f"(e.g. 'manage-users')"
        )
    if tokens[0] not in verb_lexicon():
        return False, (
            f"leading token {tokens[0]!r} of {slug!r} is not a verb in the convention "
            f"verb lexicon; start the {artifact} name with an action verb"
        )
    connective = next((t for t in tokens if t in _CONNECTIVES), None)
    if connective is not None:
        return False, (
            f"{slug!r} contains the connective {connective!r}; a verb-object name is a "
            f"verb plus a noun object, not a phrase"
        )
    return True, None
