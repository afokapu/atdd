# URN: component:govern-lifecycle:enforcement-substrate:plan_paths:backend:domain
# Runtime: python
# Purpose: Single source for locating plan/ artifacts whose on-disk home mirrors a typed identity (#1421 / #1548).
"""Where plan artifacts live on disk.

Typed identities (#1421) made the plan layout NESTED: a train
``train:<subject>:<slug>`` lives at ``plan/_trains/<subject>/<slug>.yaml``,
while legacy ``NNNN-slug`` trains stay flat at ``plan/_trains/<slug>.yaml``.

Every consumer that walks trains has to know both shapes. When that knowledge
is copied per consumer it drifts: the substrate acceptance walker globbed
``plan/_trains/*.yaml`` and silently saw ZERO of the repo's typed trains, so
train acceptances were invisible to the validators meant to enforce them
(#1548). This module exists so that traversal is written once.

Lives under ``coach/utils`` — the shared utility layer both ``planner`` and
``tester`` already import from (``repo``, ``theme_map``, ``disposition_gate``) —
rather than inside either archetype, so neither has to import the other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator


TRAINS_DIRNAME = "_trains"


def iter_train_files(trains_dir: Path) -> Iterator[Path]:
    """Yield every train YAML under ``trains_dir``, flat or subject-nested.

    Skips underscore-prefixed names at every level: those are registries
    (``_trains.yaml``, ``_aliases.yaml``) or control artifacts
    (``_interlockings/``), never trains.

    Order is unspecified; callers that need determinism sort the result.
    """
    if not trains_dir.is_dir():
        return
    for path in trains_dir.rglob("*.yaml"):
        rel = path.relative_to(trains_dir)
        if any(part.startswith("_") for part in rel.parts):
            continue
        yield path


def train_home(trains_dir: Path, train_id: str) -> Path:
    """The canonical on-disk home for ``train_id`` — mirrors its identity.

    ``train:<subject>:<slug>`` -> ``<trains_dir>/<subject>/<slug>.yaml``
    ``NNNN-slug``              -> ``<trains_dir>/NNNN-slug.yaml``

    A typed id must never be pasted straight onto a path: ``train:a:b.yaml``
    would be a colon-named file.
    """
    subject_slug = _typed_parts(train_id)
    if subject_slug is not None:
        subject, slug = subject_slug
        return trains_dir / subject / f"{slug}.yaml"
    return trains_dir / f"{train_id}.yaml"


def e2e_home(e2e_root: Path, train_id: str) -> Path:
    """The e2e home for ``train_id``. Mirrors :func:`train_home`'s nesting.

    ``train:<subject>:<slug>`` -> ``<e2e_root>/<subject>/<slug>/``
    ``NNNN-slug``              -> ``<e2e_root>/NNNN-slug/``
    """
    subject_slug = _typed_parts(train_id)
    if subject_slug is not None:
        subject, slug = subject_slug
        return e2e_root / subject / slug
    return e2e_root / train_id


def _typed_parts(train_id: str) -> tuple[str, str] | None:
    """``(subject, slug)`` for a typed train id, else ``None`` (legacy form)."""
    if not train_id.startswith("train:"):
        return None
    parts = train_id[len("train:"):].split(":")
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    return None
