# URN: test:govern-lifecycle:govern-lifecycle:C024-UNIT-001-a-registered-train-resolves-in-either-vocabulary
# Acceptance: acc:govern-lifecycle:C024-UNIT-001-a-registered-train-resolves-in-either-vocabulary
# WMBT: wmbt:govern-lifecycle:C024
# Phase: RED
# Layer: application
"""C024-UNIT-001 — a train's REGISTRATION decides the verdict, not its spelling.

Driven through the real `_validate_train_against_trains_yaml`, over a real
`plan/` written to a tmp dir, rather than over the pure normalizer alone: the
defect is that this method compares two vocabularies with `==`, so a test that
only exercised the normalizer could pass while the gate stayed broken.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager


def _plan(root: Path) -> Path:
    """A registry holding one BARE stem and one TYPED URN — the real mixture.

    Both shapes are live in this repository: 9 bare stems (the numbered
    enforcement family, harvested from `plan/_trains/*.yaml`) and 13 typed URNs.
    """
    plan = root / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text(textwrap.dedent("""\
        trains:
          0-commons:
            00-commons-nominal:
            - train_id: train:self-compliance:validate-lifecycle
              path: plan/_trains/self-compliance/validate-lifecycle.yaml
        """), encoding="utf-8")
    # A loose train file: the registry reader harvests its bare stem, while the
    # traceability graph mints `train:<stem>` for the very same file.
    (plan / "_trains" / "0007-enforce-extension-conventions.yaml").write_text(
        "train_id: 0007-enforce-extension-conventions\n", encoding="utf-8")
    return root


@pytest.mark.coder
def test_a_bare_registered_train_resolves_when_the_value_carries_the_prefix(tmp_path):
    """The store records `train:0007-...`; the registry holds `0007-...`."""
    mgr = IssueManager(target_dir=_plan(tmp_path))

    valid, messages = mgr._validate_train_against_trains_yaml(
        "train:0007-enforce-extension-conventions")

    assert valid, (
        "the train IS registered — the registry harvested it from "
        "plan/_trains/0007-enforce-extension-conventions.yaml — and the value is "
        f"exactly what the graph mints for that file: {messages}"
    )
    assert any("0007-enforce-extension-conventions" in m for m in messages), (
        "an accepting gate must still name the train it accepted"
    )


@pytest.mark.coder
def test_a_typed_registered_train_still_resolves_when_the_value_carries_the_prefix(tmp_path):
    """The 13 trains that work today must keep working."""
    mgr = IssueManager(target_dir=_plan(tmp_path))

    valid, _ = mgr._validate_train_against_trains_yaml(
        "train:self-compliance:validate-lifecycle")

    assert valid, "a typed URN registered as a typed URN must not regress"


@pytest.mark.coder
def test_a_typed_registered_train_resolves_when_the_value_omits_the_prefix(tmp_path):
    """Normalization is symmetric, not a one-way strip of the candidate.

    Either side may be spelled either way — the registry itself holds both
    shapes — so normalizing only the incoming value would leave the mirror-image
    of this defect in place.
    """
    mgr = IssueManager(target_dir=_plan(tmp_path))

    valid, _ = mgr._validate_train_against_trains_yaml(
        "self-compliance:validate-lifecycle")

    assert valid, "the registry entry is typed; the candidate is bare; same train"
