# Component: component:define-plans:artifact-naming:VerbObjectCorpus:backend:domain
"""Verb-object drift across the authored corpus (#1943).

`planner.wagon.name-is-verb-object` and `planner.feature.name-is-verb-object`
gate the AUTHORING path — `confirm_naming` reads `session.kept_units()`, so
anything authored through `atdd plan` conforms by construction. Neither looks at
what is already on disk, so an artifact renamed by hand, or created before the
rules existed, drifts with nothing to notice.

This is the corpus half: a pure scanner over names, plus the walk that collects
them. It reports; it never blocks — the disposition lives on the convention node
and is advisory, because 101 of 229 authored artifacts do not conform and
renaming one wagon touches roughly 54 files.

The scanner takes NAMES, not paths, so the judgement is testable without a
filesystem and the walk is a separate, trivially-checkable concern.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import yaml

from atdd.planner.naming import is_verb_object

__all__ = ["Drift", "corpus_names", "scan_corpus", "scan_names"]

#: Causes are kept apart because their REMEDIES differ. A noun-led name gets
#: renamed. An `and`-connective name may instead mean the artifact does two
#: jobs, which is a decomposition question, not a naming one. Collapsing them
#: into one count would hide that distinction and make the report a number.
CAUSE_NOT_A_VERB = "leading-token-not-a-verb"
CAUSE_CONNECTIVE = "connective"


@dataclass(frozen=True)
class Drift:
    """One non-conforming name, and why it does not conform."""
    artifact_kind: str   # "wagon" | "feature"
    slug: str
    cause: str
    reason: str          # the mechanic's own words, carried through verbatim


def scan_names(names: Iterable[Tuple[str, str]]) -> List[Drift]:
    """Report every non-conforming name in ``(artifact_kind, slug)`` pairs.

    Judgement is delegated to :func:`atdd.planner.naming.is_verb_object` — the
    same mechanic the Ratify gate calls — so the corpus report and the authoring
    gate can never disagree about what a verb is. This function only classifies
    the refusal it gets back.
    """
    return [d for d in (_drift(kind, slug) for kind, slug in names) if d is not None]


def _drift(artifact_kind: str, slug: str) -> "Drift | None":
    """The finding for one name, or None when it conforms."""
    ok, reason = is_verb_object(slug, artifact=artifact_kind)
    if ok:
        return None
    cause = CAUSE_CONNECTIVE if "connective" in (reason or "") else CAUSE_NOT_A_VERB
    return Drift(artifact_kind=artifact_kind, slug=slug, cause=cause,
                 reason=reason or "")


def corpus_names(plan_root: Path) -> List[Tuple[str, str]]:
    """Every authored wagon and feature name under ``plan_root``.

    Registry directories (``_trains/``, ``_substrate_anchors/``) are skipped:
    they hold registries and interlockings, not wagons, and a registry has no
    verb-object obligation.
    """
    names: List[Tuple[str, str]] = []
    if not plan_root.is_dir():
        return names

    for manifest in sorted(plan_root.glob("*/_*.yaml")):
        if manifest.parent.name.startswith("_"):
            continue
        doc = _read(manifest)
        if isinstance(doc, dict) and isinstance(doc.get("wagon"), str):
            names.append(("wagon", doc["wagon"]))

    for feature in sorted(plan_root.glob("*/features/*.yaml")):
        doc = _read(feature)
        if not isinstance(doc, dict):
            continue
        urn = doc.get("urn")
        if isinstance(urn, str) and urn:
            # `feature:<wagon>:<name>` — the name is the last segment. Quotes
            # survive in some authored files; strip before splitting.
            names.append(("feature", urn.strip('"').split(":")[-1]))
    return names


def scan_corpus(plan_root: Path) -> List[Drift]:
    """:func:`scan_names` over :func:`corpus_names` — the whole authored corpus."""
    return scan_names(corpus_names(plan_root))


def _read(path: Path):
    """Parse ``path``, or return None. A malformed plan file is another
    validator's business; this one must not fail on it."""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
