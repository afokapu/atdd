# URN: component:govern-lifecycle:train-identity-resolves-across-vocabularies:train_identity:backend:domain
# Runtime: python
# Purpose: One identity for a train, so a gate decides on registration and not on spelling (#1850).

"""Train identity, normalized — because this repository spells it two ways.

The traceability graph mints a train file sitting loose under `plan/_trains/`
as the two-part `train:<stem>` (`graph_builder.py`), while subject-scoped trains
get the three-part `train:<subject>:<slug>`. The State Store records whatever the
graph minted. The registry reader (`IssueManager._registered_train_ids`) reads
that SAME directory and returns the bare `<stem>`.

Both vocabularies are live: measured on this checkout, 13 registered ids are
typed URNs and 9 are bare stems. So neither side can be assumed prefixed or
unprefixed, and comparing them raw makes a train's registration depend on which
reader happened to produce the string — `train:0007-enforce-extension-conventions`
and `0007-enforce-extension-conventions` are one train that fails an `==`.

This module does not pick a winner between the two spellings. Rewriting what the
graph mints would rewrite recorded history in the store; rewriting the registry
would break every reader of the numbered families. Normalizing at the point of
COMPARISON leaves both sources untouched and costs one function.

NOT a parser. `plan_paths._typed_parts` and `train_urn_migration._split_typed`
already split a TYPED id into (subject, slug) and return None for the legacy
two-part form — neither can answer "are these the same train?", which is the only
question here.
"""
from __future__ import annotations

import re
from typing import Iterable, NamedTuple, Set

_PREFIX = "train:"


def normalize_train_id(train_id: str) -> str:
    """The comparable identity of *train_id*, with any `train:` prefix removed.

    Removing the prefix rather than adding one is deliberate: a bare stem has no
    unambiguous typed form to expand into (`0007-enforce-extension-conventions`
    is one segment, not `subject:slug`), so stripping is the only direction that
    is total over both vocabularies.
    """
    return train_id.strip().removeprefix(_PREFIX)


def normalize_train_ids(train_ids: Iterable[str]) -> Set[str]:
    """`normalize_train_id` over a registry, dropping ids that normalize to nothing.

    A bare `train:` normalizes to the empty string. Keeping it would let that
    value match a registry which never declared it — the false ACCEPT, which is
    strictly worse than the false reject this module exists to remove.
    """
    normalized = {normalize_train_id(t) for t in train_ids}
    normalized.discard("")
    return normalized


# --- Write-time admission (#1890) -------------------------------------------
# The read path (the PLANNED transition gate) has always checked registration.
# The write path — `atdd update <N> --train <T>` — checked nothing, so an
# unregistered id was stored and only refused later, at a gate the operator hits
# minutes or days afterwards. `0003-author-substrate` reached the repo's own
# smoke tests that way and resolves against nothing to this day.
#
# Both paths now decide through THIS function. Two callers spelling the
# admission rule separately is exactly the divergence #1850 removed one layer up.

_LEGACY_RE = re.compile(r"^(?:train:)?[0-9]{4}-[a-z0-9-]+$")


class TrainVerdict(NamedTuple):
    """Whether *train_id* may be written, and what to tell the operator.

    ``resolves`` is the admission decision and nothing else. Shape is reported
    separately in ``legacy_format`` because the two questions have different
    answers right now: `train.schema.json` states the legacy `NNNN-slug` form is
    "still accepted DURING the migration transition ... and is retired once
    worker C4 relocates every train", and 7 of the 21 registered trains are
    still spelled that way. Refusing the SHAPE today would orphan trains that
    are correctly declared; refusing the unregistered VALUE strands nothing.
    """

    resolves: bool
    legacy_format: bool
    detail: str


def check_train_id(train_id: str, known_ids: Iterable[str]) -> TrainVerdict:
    """Decide whether *train_id* may be recorded, against the declared trains.

    ``known_ids`` is the registry ∪ loose-stem union the read path already
    builds. Passing it in keeps this pure and keeps the caller's plan-directory
    resolution in one place.

    An EMPTY ``known_ids`` returns ``resolves=True``: a repository that declares
    no trains constrains nothing, which is the read path's own posture. That is a
    genuine "not applicable", not a check that failed to run — a repository with
    no `plan/_trains.yaml` is a different situation from one whose registry could
    not be read, and the caller distinguishes them before reaching here.
    """
    value = train_id.strip()
    normalized = normalize_train_id(value)
    legacy = bool(_LEGACY_RE.match(value))

    if not normalized:
        return TrainVerdict(False, legacy, "empty after the `train:` prefix — names no train")

    registered = normalize_train_ids(known_ids)
    if not registered:
        return TrainVerdict(True, legacy, "no trains are declared, so nothing constrains this")

    if normalized not in registered:
        canonical = sorted(t for t in registered if not _LEGACY_RE.match(t))
        return TrainVerdict(
            False,
            legacy,
            "resolves against no entry in plan/_trains.yaml and no loose "
            "plan/_trains/*.yaml stem.\n"
            "  Declared trains:\n"
            + "\n".join(f"    train:{t}" for t in canonical[:12])
            + ("\n    ..." if len(canonical) > 12 else ""),
        )

    if legacy:
        return TrainVerdict(
            True,
            True,
            "is a registered train in the LEGACY `NNNN-slug` form. The canonical "
            "identity is `train:<subject>:<slug>` (#1421); this spelling is "
            "accepted only until the train migration completes.",
        )

    return TrainVerdict(True, False, "is a registered train")


def legacy_ids_remaining(known_ids: Iterable[str]) -> Set[str]:
    """Registered ids still spelled the legacy way.

    The condition for promoting the legacy form from a deprecation notice to a
    hard refusal is that this returns empty — a fact the code can check, rather
    than a migration milestone somebody has to remember.
    """
    return {t for t in normalize_train_ids(known_ids) if _LEGACY_RE.match(t)}
