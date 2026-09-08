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

from typing import Iterable, Set

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
