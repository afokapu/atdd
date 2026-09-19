"""One reading of a contract's identity and provenance, shared by every consumer.

`atdd author contract` writes a schema whose provenance sits under
`x-artifact-metadata.producers` — a LIST, in the same shape as the
`_contracts.yaml` registry entry, so that "the schema file and the registry
never disagree" (author.py).

Three readers disagreed with it anyway: each reads ``metadata["producer"]``,
singular, which the writer never emits. The default fails silently — an absent
key reads as an authored blank rather than as a key that was never there.

(The same three readers also re-derive the contract URN as
``f"contract:{schema_id}"``, doubling a prefix the writer already applied. That
is #2043's, and its analysis is the opposite of the obvious one: the readers
implement the written convention and the WRITER is wrong. Left alone here.)

Putting both readings in one place is the point: a writer and its readers
cannot drift apart across a function call the way they drifted across three
modules.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

def contract_producers(metadata: Mapping[str, Any] | None) -> list[str]:
    """Every producing wagon named by ``x-artifact-metadata``, as a list.

    Accepts the plural list the writer emits, the singular scalar the legacy
    corpus carries, and `produced_by`, which the author-side spec accepts. A
    reader that understands one spelling reports "no producer" for artifacts
    that name one.
    """
    if not isinstance(metadata, Mapping):
        return []
    plural = metadata.get("producers") or metadata.get("produced_by")
    if isinstance(plural, str):
        return [plural]
    if isinstance(plural, Sequence):
        return [str(p) for p in plural if p]
    singular = metadata.get("producer")
    return [str(singular)] if singular else []


def contract_producer(metadata: Mapping[str, Any] | None) -> str:
    """The single producer spelling the registry row and the traceability
    report carry. Empty only when the artifact genuinely names none."""
    producers = contract_producers(metadata)
    return producers[0] if producers else ""
