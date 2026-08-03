# URN: test:isolate-provider-boundary:define-provider-interface:D001-UNIT-002-protocol-shape-holds
# Acceptance: acc:isolate-provider-boundary:D001-UNIT-002-protocol-shape-holds
# WMBT: wmbt:isolate-provider-boundary:D001
# Phase: GREEN
# Layer: unit
# Runtime: python
# Assertion: behavioral
# Purpose: A conforming in-memory implementation satisfies the SyncProvider Protocol structurally (name, mirror, detect_drift, digest) without importing core; mirror() takes list[ObjectSnapshot] and returns list[ExternalRefUpdate]; digest() returns an ExtensionDigest carrying a version and a sha256 digest — and an implementation missing a method is reported as missing it. Refs #1400.
"""The seam is satisfiable from outside, and its shape is checkable (D001-UNIT-002).

wagon: isolate-provider-boundary | feature: define-provider-interface | phase: GREEN
WMBT: wmbt:isolate-provider-boundary:D001

The conforming implementation used here **does not import core**. That is the acceptance, not a
detail of the fixture: a real provider lives in another repository, and if satisfying the seam
required inheriting from a core base class then the boundary law (*provider code imports core; core
never imports provider code*) would be satisfiable in one direction only. It duck-types, and the
Protocol is structural, and that is why an extension can exist at all.

Core's side of the conversation is checked too: what a provider is *handed* is an ``ObjectSnapshot``
— a frozen copy, not the document — so "the extension never edits the projection" is true because
it has nothing to edit, not because it chose not to.
"""
from __future__ import annotations

import dataclasses

from atdd.state import provider_seam
from atdd.state.provider_seam import ExternalRefUpdate, ObjectSnapshot

from ._seam import UID_X, UID_Y, StubProvider, document, projection


def test_d001_unit_002_protocol_shape_holds() -> None:
    """A conforming provider satisfies the Protocol; the types flow in and out as declared."""
    provider = StubProvider(name="demo", version="2.1.0")

    ok, missing = provider_seam.satisfies_protocol(provider)
    assert ok, f"a conforming provider is missing {missing}"
    assert missing == []
    assert isinstance(provider.name, str)

    # It never imported core to get here — the Protocol is structural, which is the only way a
    # provider in another repository could satisfy it.
    assert type(provider).__module__.endswith("_seam")
    assert not any(
        base.__module__.startswith("atdd.") for base in type(provider).__mro__[1:]
    ), "a conforming provider inherits nothing from core"

    # mirror() accepts list[ObjectSnapshot]...
    documents = projection(document(UID_X), document(UID_Y, slug="feature-y"))
    snapshots = [ObjectSnapshot.of(documents[uid]) for uid in sorted(documents)]
    assert [snapshot.uid for snapshot in snapshots] == [UID_X, UID_Y]
    assert dataclasses.is_dataclass(snapshots[0]) and _frozen(ObjectSnapshot), (
        "a snapshot is a frozen copy: the provider has nothing to edit, so it cannot"
    )

    # ...and returns records the seam admits as ExternalRefUpdates.
    emitted = provider.mirror(snapshots)
    admitted = [provider_seam.validate_update(ref, provider="demo") for ref in emitted]
    assert len(admitted) == 2
    assert all(isinstance(update, ExternalRefUpdate) for update in admitted)
    assert all(update.namespace == "bot:demo" for update in admitted)
    assert all(update.authoritative is False for update in admitted)
    assert {update.uid for update in admitted} == {UID_X, UID_Y}

    # detect_drift() is alarm-only, and returns alarms (here, none).
    assert provider.detect_drift(snapshots) == []

    # digest() returns an ExtensionDigest carrying a version and a sha256 digest.
    stamp = provider.digest()
    assert stamp.name == "demo"
    assert stamp.version == "2.1.0"
    assert stamp.digest.startswith("sha256:")
    assert len(stamp.digest) == len("sha256:") + 64


def test_d001_unit_002_a_non_conforming_object_is_told_what_it_lacks() -> None:
    """The Protocol check reports what is missing — a provider author needs the list, not a bool."""

    class HalfAProvider:
        name = "half"

        def mirror(self, objects):
            return []

    ok, missing = provider_seam.satisfies_protocol(HalfAProvider())

    assert not ok
    assert missing == ["detect_drift()", "digest()"]

    ok, missing = provider_seam.satisfies_protocol(object())
    assert not ok
    assert "name: str" in missing


def _frozen(cls) -> bool:
    return bool(cls.__dataclass_params__.frozen)  # type: ignore[attr-defined]
