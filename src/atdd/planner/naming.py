# Component: component:atdd-plan-core:naming:VerbObjectRule:backend:domain
"""Foundational verb-object naming rule for planner artifacts (#1276).

``wagon`` and ``feature`` slugs are documented as verb-object by
``planner.wagon.name-is-verb-object`` / ``planner.feature.name-is-verb-object``
but, before #1276, this was prose "preference" with no enforcement. This module
is the pure, testable mechanic both the ``atdd validate planner`` validators and
the ``atdd plan`` Confirm gate use.

Mechanic (pragmatic, not NLP):
  1. slug is kebab-case ``^[a-z][a-z0-9]*(-[a-z0-9]+)*$``;
  2. slug has >= 2 tokens (a verb and an object);
  3. the leading token is a verb in the convention **verb lexicon** — the union
     of the ``verbs_by_type`` suggestion verbs and the explicit
     ``additional_verbs`` allowlist, both carried as terms on the
     ``planner.feature.verb-selection-by-artifact-type`` convention node;
  4. no token is a connective (``and``/``or``/``to``/...): a verb-object name is a
     verb plus a noun object, not a phrase.

A slug listed explicitly in the node's optional ``brand_exceptions`` term (per
artifact) is allowed to bypass the rule — brand/proper-noun exceptions must be
*explicit in the convention*, never implicit.

Source of truth (#1639): the convention **nodes**. This module used to execute
``feature.convention.yaml`` / ``wagon.convention.yaml`` directly; those legacy
monoliths carried 0 live rules and were deleted, so the lexicon now lives where
the rule that uses it lives. Cycle-safe by the same discipline as before: a
plain ``yaml`` read of the node file, no coach/graph import.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

import yaml

_NODES_DIR = Path(__file__).resolve().parent / "conventions" / "nodes"

# The node carrying the verb lexicon (both halves) and the brand-exception hatch.
_VERB_NODE = "planner.feature.verb-selection-by-artifact-type.convention.yaml"

_KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

# Connectives forbidden in a verb-object slug — their presence signals a phrase
# (``route-to-mode``, ``respond-and-preview``) rather than verb + noun object.
_CONNECTIVES = frozenset({
    "and", "or", "to", "for", "of", "with", "the", "a", "an",
    "in", "on", "by", "via", "from", "at", "as", "into", "onto",
})


def _node_terms(filename: str) -> dict:
    """``{term_id: values}`` for one convention node; ``{}`` when absent."""
    path = _NODES_DIR / filename
    if not path.exists():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        t.get("term_id"): (t.get("values") or {})
        for t in (doc.get("terms") or [])
        if isinstance(t, dict) and t.get("term_id")
    }


@lru_cache(maxsize=1)
def verb_lexicon() -> frozenset:
    """The canonical allowed-leading-verb set.

    Union of the ``verbs_by_type`` suggestion verbs (the historical
    ``verb_selection.by_artifact_type`` table) and the explicit
    ``additional_verbs`` allowlist — so the rule has a complete basis instead of
    the 21-verb suggestion table, which rejects even the convention's own
    examples (#1276)."""
    terms = _node_terms(_VERB_NODE)
    verbs: set = set()
    for bucket in (terms.get("verbs_by_type") or {}).values():
        # Node form is ``{artifact_type: [verb, ...]}``; tolerate the legacy
        # ``{artifact_type: {verbs: [...]}}`` shape the monolith used.
        if isinstance(bucket, dict):
            bucket = bucket.get("verbs") or []
        verbs.update(bucket or [])
    verbs.update((terms.get("additional_verbs") or {}).get("additional_verbs") or [])
    return frozenset(verbs)


@lru_cache(maxsize=4)
def brand_exceptions(artifact: str) -> frozenset:
    """Explicit brand/proper-noun slugs allowed to bypass verb-object.

    Read from the node's optional ``brand_exceptions`` term, keyed by artifact
    (``wagon`` / ``feature``). The term carries no entries today — both legacy
    ``verb_object_enforcement.brand_exceptions`` lists were empty — but the
    hatch is retained so an exception can be declared in the convention rather
    than hardcoded in a validator."""
    block = _node_terms(_VERB_NODE).get("brand_exceptions") or {}
    return frozenset(block.get(artifact) or ())


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
