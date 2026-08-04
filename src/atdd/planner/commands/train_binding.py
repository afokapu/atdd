# Component: component:author-atdd-substrate:author-issue-body:TrainBinding:backend:domain
"""The issue↔train binding primitive (#1590).

One place that answers three questions about a declared train reference:

* is it shaped like a train identity at all (``is_train_id``)?
* does it resolve to a train this repository REGISTERS (``resolve_train``)?
* does that registered train have an INTERLOCKING (``resolve_train.interlockings``)?

BOUNDARY: this lives planner-side deliberately, exactly as ``feature_binding``
does. ``author_publish.publish_issue`` / ``revise_issue`` must validate a train
reference before they write, and the planner tree may NOT ``import atdd.coach``
(planner.theme.commons-coach-boundary, #970). The coach validator DELEGATES
here — the dependency points coach → planner, never the reverse.

CONSUMER-REPOSITORY NEUTRALITY IS THE POINT, not a follow-up. Nothing here
knows atdd's train ids, atdd's subjects, or atdd's directory idiom. A consumer
repo declares its own trains through the same substrate, so every lookup is
driven off the repo's OWN ``plan/_trains.yaml``, its OWN
``plan/_trains/_aliases.yaml`` and its OWN interlocking home, resolved against
whatever root the caller passes. A repo with no ``plan/`` tree is not in
violation of anything — it has no registry to resolve against, and
``plan_is_available`` says so.

Registration is read from TWO places on purpose, mirroring the shipped
``TrainResolver`` rather than inventing a stricter rule than the resolver the
repo already ships:

* the registry index ``plan/_trains.yaml`` (canonical ``train_id`` entries), and
* the per-train manifest the identity implies on disk
  (``plan/_trains/<subject>/<slug>.yaml``, or the legacy flat
  ``plan/_trains/<NNNN-slug>.yaml``).

Either is registration. A consumer repo that authors train manifests without
maintaining the index is not reported for it, and a legacy id still resolves
through the migration alias map (#1421) — which is exactly the dual-resolution
window ``TrainResolver`` documents.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from atdd.planner.commands.feature_binding import plan_is_available, plan_root

logger = logging.getLogger(__name__)

__all__ = [
    "TrainBinding",
    "TRAINS_REGISTRY",
    "TRAIN_ALIASES",
    "interlocking_index",
    "is_train_id",
    "plan_is_available",
    "plan_root",
    "registered_trains",
    "resolve_train",
    "train_aliases",
    "train_in_body",
    "train_relpath",
]

#: The registry index and the migration alias map, repo-relative.
TRAINS_REGISTRY = "plan/_trains.yaml"
TRAIN_ALIASES = "plan/_trains/_aliases.yaml"

#: ``train:<subject>:<slug>`` — the typed identity (#1421).
_TYPED_TRAIN_RE = re.compile(r"^train:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$")

#: ``NNNN-slug`` — the legacy flat id still resolvable through the alias map.
_LEGACY_TRAIN_RE = re.compile(r"^\d{4}-[a-z0-9][a-z0-9-]*$")

#: The body's Metadata table row, e.g. ``| Train | `train:s:x` |``.
_BODY_TRAIN_RE = re.compile(
    r"(?im)^\s*\|\s*Train\s*\|\s*`?\s*([^\s|`]+)\s*`?\s*\|"
)


def is_train_id(value: Optional[str]) -> bool:
    """True when ``value`` is shaped like a train identity.

    Both accepted spellings count: the typed ``train:<subject>:<slug>`` and the
    legacy flat ``NNNN-slug`` the alias map still resolves. A placeholder
    (``TBD``, ``N/A``), a bare subject, or a feature URN is not a train
    identity and is reported as malformed rather than merely unresolved — the
    caller can then be told which of the two shapes to write.
    """
    text = (value or "").strip()
    if not text:
        return False
    return bool(_TYPED_TRAIN_RE.match(text) or _LEGACY_TRAIN_RE.match(text))


def train_in_body(body: Optional[str]) -> Optional[str]:
    """The Train value the issue body's Metadata table declares, if any."""
    match = _BODY_TRAIN_RE.search(body or "")
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def train_relpath(train_id: str) -> str:
    """The repo-relative per-train manifest path a train identity implies.

    Typed ids nest under their subject; the legacy flat id keeps its flat home.
    Mirrors ``atdd.planner.commands.author.train_relpath`` — kept here rather
    than imported so this module stays free of the authoring command's import
    graph, and pinned to it by a test.
    """
    text = (train_id or "").strip()
    if _TYPED_TRAIN_RE.match(text):
        subject, slug = text[len("train:"):].split(":", 1)
        return f"plan/_trains/{subject}/{slug}.yaml"
    return f"plan/_trains/{text}.yaml"


@dataclass(frozen=True)
class TrainBinding:
    """A declared train reference plus its verdict against the repo's registry."""

    urn: Optional[str]
    resolved: bool
    reason: Optional[str]          # None | "unbound" | "malformed" | "unresolved"
    #: The canonical registered id the reference resolved to (an alias resolves
    #: to the typed id it names, so a consumer reads one value either way).
    train_id: Optional[str] = None
    path: Optional[Path] = None
    #: Interlocking ids whose routes cover the resolved train ([] when none).
    interlockings: List[str] = field(default_factory=list)
    detail: str = ""

    @property
    def has_interlocking(self) -> bool:
        """True when the resolved train is covered by at least one interlocking."""
        return bool(self.interlockings)


# ---------------------------------------------------------------------------
# Registry reads — tolerant of absence and of shape, never raising
# ---------------------------------------------------------------------------
def _read_yaml(path: Path, *, what: str) -> Optional[Any]:
    """Parse ``path``, or return None having SAID SO when it cannot be read.

    Observably react, never merely return (coder.logging.coach-silent-swallow):
    a registry an operator believes is being consulted, and which is in fact
    unparseable, is precisely the silent hole this whole rule exists to close.
    """
    if not path.is_file():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        logger.warning(
            "train registry is unreadable; treating it as empty",
            extra={"what": what, "path": str(path), "error": str(exc)},
        )
        return None


def registered_trains(start: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """``{train_id: entry}`` for every train the repo's registry index declares.

    Walks the nested ``trains: {group: {bucket: [entry]}}`` shape without
    assuming any particular group or bucket naming — a consumer repo buckets by
    its own subjects, and this must not care.
    """
    doc = _read_yaml(plan_root(start).parent / TRAINS_REGISTRY, what="trains-registry")
    if not isinstance(doc, dict):
        return {}
    trains = doc.get("trains")
    if not isinstance(trains, dict):
        return {}

    found: Dict[str, Dict[str, Any]] = {}
    for buckets in trains.values():
        if not isinstance(buckets, dict):
            continue
        for entries in buckets.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                train_id = str(entry.get("train_id") or "").strip()
                if train_id:
                    found.setdefault(train_id, entry)
    return found


def train_aliases(start: Optional[Path] = None) -> Dict[str, str]:
    """``{legacy_id: canonical_typed_id}`` from the migration alias map (#1421).

    Tolerant of every shape the map has been authored in: a top-level
    ``aliases:`` mapping or a bare mapping, keys optionally ``train:``-prefixed,
    values spelled ``subject/slug`` | ``subject:slug`` | ``train:subject:slug``.
    """
    doc = _read_yaml(plan_root(start).parent / TRAIN_ALIASES, what="train-aliases")
    if not isinstance(doc, dict):
        return {}
    mapping = doc.get("aliases") if isinstance(doc.get("aliases"), dict) else doc
    if not isinstance(mapping, dict):
        return {}

    aliases: Dict[str, str] = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        legacy = key[len("train:"):] if key.startswith("train:") else key
        typed = _canonical_from_alias_value(value)
        if legacy.strip() and typed:
            aliases[legacy.strip()] = typed
    return aliases


def _canonical_from_alias_value(value: str) -> Optional[str]:
    """``subject/slug`` | ``subject:slug`` | ``train:subject:slug`` -> typed id."""
    text = value.strip()
    if not text:
        return None
    if text.startswith("train:"):
        return text if _TYPED_TRAIN_RE.match(text) else None
    parts = re.split(r"[/:]", text)
    if len(parts) != 2 or not all(parts):
        return None
    candidate = f"train:{parts[0]}:{parts[1]}"
    return candidate if _TYPED_TRAIN_RE.match(candidate) else None


# ---------------------------------------------------------------------------
# Interlocking coverage — which interlocking(s) route through a given train
# ---------------------------------------------------------------------------
def interlocking_index(start: Optional[Path] = None) -> Dict[str, List[str]]:
    """``{train_key: [interlocking_id]}`` over the repo's declared interlockings.

    A train is keyed BOTH by its declared ``train_id`` and by its
    ``train_path``, because a route may name either and the two spellings must
    agree on one answer. Reading the interlocking home through
    ``planner.interlocking.discovery`` is what keeps this consumer-neutral:
    the home is derived from the caller's root, never from atdd's own layout.
    """
    from atdd.planner.interlocking.discovery import iter_interlocking_paths

    root = plan_root(start).parent
    index: Dict[str, List[str]] = {}
    for path in iter_interlocking_paths(root):
        doc = _read_yaml(path, what="interlocking")
        if not isinstance(doc, dict):
            continue
        interlocking_id = str(doc.get("interlocking_id") or path.stem).strip()
        for route in doc.get("routes") or []:
            if not isinstance(route, dict):
                continue
            for key in _route_train_keys(route):
                bucket = index.setdefault(key, [])
                if interlocking_id not in bucket:
                    bucket.append(interlocking_id)
    return index


def _route_train_keys(route: Dict[str, Any]) -> Tuple[str, ...]:
    """Every key a route offers for matching the train it drives."""
    keys: List[str] = []
    train_id = str(route.get("train_id") or "").strip()
    if train_id:
        keys.append(train_id)
    train_path = str(route.get("train_path") or "").strip()
    if train_path:
        keys.append(Path(train_path).as_posix())
    return tuple(keys)


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def resolve_train(
    urn: Optional[str],
    start: Optional[Path] = None,
    *,
    interlockings: Optional[Dict[str, List[str]]] = None,
) -> TrainBinding:
    """Resolve a declared train reference against the repo rooted at ``start``.

    Never raises: the verdict IS the return value, so the write-side guard and
    the read-side validator can both report rather than explode.

    ``interlockings`` accepts a pre-built :func:`interlocking_index` so a
    caller resolving many references pays for the interlocking scan once.
    """
    text = (urn or "").strip()
    if not text:
        return TrainBinding(
            urn=None, resolved=False, reason="unbound",
            detail="the issue carries no train reference",
        )

    if not is_train_id(text):
        return TrainBinding(
            urn=text, resolved=False, reason="malformed",
            detail=(
                f"{text!r} is not a train identity; expected "
                f"train:<subject>:<slug> (or the legacy NNNN-slug form)"
            ),
        )

    registry = registered_trains(start)
    root = plan_root(start).parent

    canonical, alias_of = _canonicalize(text, registry, train_aliases(start))
    entry = registry.get(canonical)
    declared_path = str((entry or {}).get("path") or "").strip()
    relpath = Path(declared_path).as_posix() if declared_path else train_relpath(canonical)
    manifest = root / relpath

    if entry is None and not manifest.is_file():
        return TrainBinding(
            urn=text, resolved=False, reason="unresolved",
            detail=_unresolved_detail(text, canonical, registry, relpath),
        )

    index = interlocking_index(start) if interlockings is None else interlockings
    covering = _covering_interlockings(canonical, text, relpath, index)

    how = f" (alias of {canonical})" if alias_of else ""
    return TrainBinding(
        urn=text, resolved=True, reason=None, train_id=canonical,
        path=manifest, interlockings=covering,
        detail=(
            f"train {text}{how} is registered in {TRAINS_REGISTRY}"
            if entry is not None
            else f"train {text}{how} is registered by its manifest at {relpath}"
        ),
    )


def _canonicalize(
    text: str, registry: Dict[str, Dict[str, Any]], aliases: Dict[str, str],
) -> Tuple[str, bool]:
    """``(canonical_id, was_alias_resolved)``.

    A reference the registry declares VERBATIM is already canonical — checked
    first so a repo that still registers legacy ids is not forced through the
    alias map to be recognized.
    """
    if text in registry:
        return text, False
    typed = aliases.get(text)
    if typed:
        return typed, True
    return text, False


def _covering_interlockings(
    canonical: str, declared: str, relpath: str, index: Dict[str, List[str]],
) -> List[str]:
    """Interlocking ids whose routes cover this train, under any of its keys."""
    covering: List[str] = []
    for key in (canonical, declared, relpath):
        for interlocking_id in index.get(key, ()):
            if interlocking_id not in covering:
                covering.append(interlocking_id)
    return covering


def _unresolved_detail(
    declared: str, canonical: str, registry: Dict[str, Dict[str, Any]], relpath: str,
) -> str:
    """Name the registry, the path probed, and the resolvable candidates.

    A violation that does not say what WOULD have resolved makes the reader
    re-derive the registry contents by hand — which is how the 2026-07-22 store
    recovery came to verify 82 trains manually.
    """
    resolved_via = "" if canonical == declared else f" (alias-resolved to {canonical})"
    candidates = sorted(registry)
    shown = ", ".join(candidates[:8]) or "(the registry declares no trains)"
    more = f", … {len(candidates) - 8} more" if len(candidates) > 8 else ""
    return (
        f"train {declared}{resolved_via} is not registered: absent from "
        f"{TRAINS_REGISTRY} and no manifest at {relpath}. "
        f"Registered trains: {shown}{more}"
    )
