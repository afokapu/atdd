# URN: test:govern-lifecycle:govern-lifecycle:C024-UNIT-002-an-unregistered-train-is-still-rejected
# Acceptance: acc:govern-lifecycle:C024-UNIT-002-an-unregistered-train-is-still-rejected
# WMBT: wmbt:govern-lifecycle:C024
# Phase: RED
# Layer: application
"""C024-UNIT-002 — the teeth survive the fix.

Normalizing identity must not become accepting anything. The gate exists to
refuse a train the registry never declared, and a "fix" that widened it into a
pass would be strictly worse than the defect: a false reject wedges one issue
loudly, a false accept lets every unregistered train through silently.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atdd.coach.commands.issue import IssueManager


def _plan(root: Path) -> Path:
    plan = root / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_trains.yaml").write_text(textwrap.dedent("""\
        trains:
          0-commons:
            00-commons-nominal:
            - train_id: train:self-compliance:validate-lifecycle
              path: plan/_trains/self-compliance/validate-lifecycle.yaml
        """), encoding="utf-8")
    (plan / "_trains" / "0007-enforce-extension-conventions.yaml").write_text(
        "train_id: 0007-enforce-extension-conventions\n", encoding="utf-8")
    return root


@pytest.mark.coder
@pytest.mark.parametrize("value", [
    "train:not-a-registered-train",
    "not-a-registered-train",
    "train:nope:also-not-registered",
    "nope:also-not-registered",
])
def test_an_unregistered_train_is_rejected_in_either_vocabulary(tmp_path, value):
    mgr = IssueManager(target_dir=_plan(tmp_path))

    valid, messages = mgr._validate_train_against_trains_yaml(value)

    assert not valid, f"{value!r} is not in the registry and must not be accepted"
    assert any(value in m for m in messages), (
        "the rejection must name the value it looked for, or the operator cannot "
        f"see what the gate searched for: {messages}"
    )


@pytest.mark.coder
def test_a_bare_prefix_does_not_match_an_empty_stem(tmp_path):
    """`train:` normalizes to the empty string; nothing may match it."""
    mgr = IssueManager(target_dir=_plan(tmp_path))

    valid, _ = mgr._validate_train_against_trains_yaml("train:")

    assert not valid, "a prefix with no train after it names no train"


@pytest.mark.coder
def test_an_empty_registry_still_short_circuits_to_accept(tmp_path):
    """A consumer repo that declares no trains is unaffected by this gate."""
    (tmp_path / "plan").mkdir()
    mgr = IssueManager(target_dir=tmp_path)

    valid, messages = mgr._validate_train_against_trains_yaml("train:anything")

    assert valid, "no trains declared means no constraint — shipped behaviour"
    assert messages == [], "a skipped cross-reference reports nothing"
