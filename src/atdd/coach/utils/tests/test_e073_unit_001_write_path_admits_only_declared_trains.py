# URN: test:govern-lifecycle:train-identity-resolves-across-vocabularies:E073-UNIT-001-write-path-admits-only-declared-trains
# Acceptance: acc:govern-lifecycle:E073-UNIT-001-write-path-admits-only-declared-trains
# WMBT: wmbt:govern-lifecycle:E073
# Phase: GREEN
# Layer: backend.unit
"""E073-UNIT-001 — the train write path admits only declared trains (#1890).

`atdd update <N> --train <T>` wrote whatever it was handed. The PLANNED gate then
refused the issue because the value named no train — a refusal the operator meets
minutes or days after the mistake, with nothing in between to connect them.

Both paths now decide through `check_train_id`. Shape is reported separately from
admission on purpose: `train.schema.json` keeps the legacy `NNNN-slug` form valid
"DURING the migration transition", and 7 of the 21 registered trains are still
spelled that way, so refusing the SHAPE would orphan trains that are correctly
declared. Refusing the unregistered VALUE strands nothing.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.train_identity import check_train_id, legacy_ids_remaining

DECLARED = [
    "train:self-compliance:validate-lifecycle",
    "train:substrate:author-artifacts",
    "0007-enforce-extension-conventions",      # registered, legacy spelling
]


def test_a_declared_canonical_train_is_admitted() -> None:
    v = check_train_id("train:self-compliance:validate-lifecycle", DECLARED)
    assert v.resolves and not v.legacy_format


def test_an_undeclared_value_is_refused() -> None:
    """The measured defect: `atdd update 1888 --train INVALID` was accepted."""
    v = check_train_id("INVALID", DECLARED)
    assert not v.resolves
    assert "resolves against no entry" in v.detail


def test_a_retired_legacy_id_is_refused(  ) -> None:
    """`0003-author-substrate` was the shipped default and names no train."""
    v = check_train_id("0003-author-substrate", DECLARED)
    assert not v.resolves
    assert v.legacy_format, "shape is still reported, so the caller can name a successor"


@pytest.mark.parametrize("spelling", [
    "0007-enforce-extension-conventions",
    "train:0007-enforce-extension-conventions",
])
def test_both_spellings_of_a_declared_legacy_train_are_admitted(spelling: str) -> None:
    """#1850's normalization, held: one train, two vocabularies, one verdict."""
    v = check_train_id(spelling, DECLARED)
    assert v.resolves and v.legacy_format


@pytest.mark.parametrize("empty", ["", "   ", "train:"])
def test_an_empty_identity_is_refused(empty: str) -> None:
    """A bare `train:` normalizes to nothing; admitting it would match a registry
    that never declared it — the false ACCEPT."""
    assert not check_train_id(empty, DECLARED).resolves


def test_a_repository_declaring_no_trains_constrains_nothing() -> None:
    """NOT_APPLICABLE, not a check that failed to run. The read path takes the
    same posture, and the caller distinguishes 'none declared' from 'could not
    read' before reaching here."""
    assert check_train_id("anything-at-all", []).resolves


def test_legacy_remaining_is_the_promotion_condition() -> None:
    """Refusing the legacy SHAPE becomes correct when this reaches zero — a fact
    the code checks, not a milestone somebody has to remember."""
    assert legacy_ids_remaining(DECLARED) == {"0007-enforce-extension-conventions"}
    assert legacy_ids_remaining(["train:substrate:author-artifacts"]) == set()
