# Component: component:atdd-plan-core:naming:ArtifactNamingRule:backend:domain
"""Foundational artifact/contract naming rule for planner artifacts (#1329).

Artifact identities (a wagon ``produce[].name``, a contract ``$id``) are
documented in ``artifact-naming.convention.yaml`` as the theme-first grammar
``{theme}(:{category})*:{aspect}(.{variant})?`` — but, before #1329, this was
prose guidance with no enforcement, so a bad theme (``round:result`` — ``round``
is not a theme) or a mis-pathed contract file passed ``atdd plan`` Confirm
silently. This module is the pure, testable mechanic the ``atdd plan`` Confirm
gate (and its bound validators) use, mirroring the verb-object mechanic in
:mod:`atdd.planner.naming` (#1276).

Two checks, both pure:

``is_valid_artifact_identity(name, config)``
    1. the identity parses as the theme-first grammar
       (``theme`` + 0+ ``category`` + ``aspect`` + optional single ``variant``);
    2. every token is kebab-case ``^[a-z][a-z0-9]*(-[a-z0-9]+)*$``;
    3. the ``theme`` is in the effective theme map ``get_theme_map(config)``
       (built-in defaults + ``.atdd/config.yaml`` ``themes:`` overrides) — the
       same single source of truth the ``planner.theme.must-be-canonical``
       validator resolves against (#1317). ``round:result`` is rejected here.

``path_mirrors_identity(name, contract_path)``
    the contract file path mirrors the identity — every ``:``/``.`` boundary
    becomes a directory boundary under ``contracts/`` and the leaf is a
    ``.schema.json`` file (``contracts/{theme}/…/{aspect}.schema.json``). Both
    convention-blessed physical forms of the simple ``theme:aspect`` identity
    (``contracts/theme/aspect.schema.json`` and the repeated-leaf
    ``contracts/theme/aspect/aspect.schema.json``) are accepted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Set, Tuple

from atdd.coach.utils.theme_map import get_theme_map

# A single identity token — theme, category, aspect, or variant — is kebab-case.
_TOKEN_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

_CONTRACTS_ROOT = "contracts/"
_SCHEMA_SUFFIX = ".schema.json"


@dataclass(frozen=True)
class ParsedIdentity:
    """The decomposed parts of a theme-first artifact identity."""

    theme: str
    categories: Tuple[str, ...]
    aspect: str
    variant: Optional[str]

    @property
    def segments(self) -> Tuple[str, ...]:
        """The identity's path segments in order: theme, categories, aspect, and
        the variant when present — i.e. every ``:``/``.``-delimited token."""
        segs: List[str] = [self.theme, *self.categories, self.aspect]
        if self.variant is not None:
            segs.append(self.variant)
        return tuple(segs)


def parse_identity(name: str) -> Tuple[Optional[ParsedIdentity], Optional[str]]:
    """Parse *name* as ``{theme}(:{category})*:{aspect}(.{variant})?``.

    Returns ``(parsed, None)`` on success or ``(None, reason)`` when the shape is
    malformed. Token kebab-case and theme-membership are checked separately by
    :func:`is_valid_artifact_identity` — this only decomposes the grammar."""
    name = name or ""
    if not name:
        return None, "empty artifact identity"
    if name.startswith(":") or name.endswith(":") or "::" in name:
        return None, f"{name!r} has an empty colon-delimited segment"

    colon_parts = name.split(":")
    if len(colon_parts) < 2:
        return None, (
            f"{name!r} has no theme separator; a theme-first identity is "
            f"'theme:aspect' at minimum (e.g. 'commons:identifiers')"
        )

    theme = colon_parts[0]
    *categories, leaf = colon_parts[1:]

    if "." in leaf:
        dot_parts = leaf.split(".")
        if len(dot_parts) != 2 or "" in dot_parts:
            return None, (
                f"aspect segment {leaf!r} of {name!r} carries more than one "
                f"variant; the grammar allows a single '.variant' facet"
            )
        aspect, variant = dot_parts[0], dot_parts[1]
    else:
        aspect, variant = leaf, None

    return (
        ParsedIdentity(
            theme=theme,
            categories=tuple(categories),
            aspect=aspect,
            variant=variant,
        ),
        None,
    )


def _theme_names(config: Optional[Mapping[str, Any]]) -> Set[str]:
    """The effective theme names for *config* — the single source of truth shared
    with ``planner.theme.must-be-canonical`` (#1317)."""
    return set(get_theme_map(config).values())


def is_valid_artifact_identity(
    name: str, *, config: Optional[Mapping[str, Any]] = None
) -> Tuple[bool, Optional[str]]:
    """Return ``(ok, reason)``. ``reason`` is ``None`` when ``ok`` is True, else a
    human-readable explanation of the first violated clause.

    Checks, in order: theme-first grammar shape, kebab-case of every token, and
    ``theme ∈ get_theme_map(config)``."""
    parsed, reason = parse_identity(name)
    if parsed is None:
        return False, reason

    for label, token in (
        ("theme", parsed.theme),
        *[("category", c) for c in parsed.categories],
        ("aspect", parsed.aspect),
        *([("variant", parsed.variant)] if parsed.variant is not None else []),
    ):
        if not _TOKEN_RE.match(token):
            return False, (
                f"{label} segment {token!r} of {name!r} is not kebab-case "
                r"(must match ^[a-z][a-z0-9]*(-[a-z0-9]+)*$)"
            )

    allowed = _theme_names(config)
    if parsed.theme not in allowed:
        return False, (
            f"theme {parsed.theme!r} of {name!r} is not in the effective theme "
            f"map {sorted(allowed)} (get_theme_map + .atdd/config.yaml themes); "
            f"start the identity with a taxonomy theme"
        )
    return True, None


def expected_contract_paths(name: str) -> Set[str]:
    """The set of contract file paths that mirror identity *name*.

    Every ``:``/``.`` boundary is a directory boundary under ``contracts/`` and
    the leaf token becomes a ``.schema.json`` file. The simple ``theme:aspect``
    identity (no category, no variant) has two convention-blessed physical forms
    — the plain ``contracts/theme/aspect.schema.json`` and the repeated-leaf
    ``contracts/theme/aspect/aspect.schema.json`` — so both are returned.
    Returns an empty set for an unparseable identity."""
    parsed, _reason = parse_identity(name)
    if parsed is None:
        return set()

    segs = list(parsed.segments)
    forms: Set[str] = {_CONTRACTS_ROOT + "/".join(segs) + _SCHEMA_SUFFIX}

    # Simple form theme:aspect (no category, no variant): the leaf gets its own
    # directory with the schema file repeated inside it.
    if not parsed.categories and parsed.variant is None:
        forms.add(
            _CONTRACTS_ROOT + "/".join(segs + [parsed.aspect]) + _SCHEMA_SUFFIX
        )
    return forms


def _normalize_path(contract_path: str) -> str:
    """Strip a leading ``./`` and collapse backslashes to forward slashes so the
    mirror check is OS- and style-agnostic."""
    p = (contract_path or "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p


def path_mirrors_identity(
    name: str, contract_path: str
) -> Tuple[bool, Optional[str]]:
    """Return ``(ok, reason)`` for whether *contract_path* mirrors identity *name*.

    Only ``.schema.json`` contract files are validated here — a null/absent
    contract or a directory-reference physical form (no ``.schema.json`` leaf) is
    out of scope for this mechanic and yields ``(True, None)`` (the caller decides
    whether a missing contract is itself a violation)."""
    path = _normalize_path(contract_path)
    if not path.endswith(_SCHEMA_SUFFIX):
        return True, None  # not a concrete schema file — nothing to mirror

    parsed, reason = parse_identity(name)
    if parsed is None:
        return False, f"cannot mirror path for unparseable identity: {reason}"

    accepted = expected_contract_paths(name)
    if path not in accepted:
        return False, (
            f"contract path {path!r} does not mirror identity {name!r}; "
            f"expected one of {sorted(accepted)}"
        )
    return True, None
