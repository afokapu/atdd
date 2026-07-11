# Component: component:atdd-plan-core:migration:TrainUrnMigration:backend:tests
# Purpose: legacy NNNN-slug <-> typed train:<subject>:<slug> alias map + rollback round-trip (#1421).
"""RED/GREEN for the train-URN migration tool (#1421 Layer 7).

The migration retypes every legacy ``NNNN-slug`` train to
``train:<subject>:<slug>``. Because ``category`` was baked into the digit
identity, the subject/slug split cannot be mechanized — it is HAND-AUTHORED in
``LEGACY_TRAIN_ALIASES``. This module pins:

* the forward map covers every legacy train present in ``plan/_trains/``,
* every forward result is a valid typed URN per the C1 engine,
* forward∘rollback is the identity (a documented, lossless inverse), and
* the on-disk alias file (``plan/_trains/_aliases.yaml``) that C2's resolver
  consults agrees with the hand-authored constant.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.graph.urn import URNGrammar
from atdd.planner.migration import train_urn_migration as mig

_REPO_ROOT = Path(__file__).resolve().parents[5]
_TRAINS_DIR = _REPO_ROOT / "plan" / "_trains"

# The five legacy trains present in this branch (0001-0005). #1400's
# 0006/0206/0306 are documented but deferred to that issue's own migration.
_EXPECTED_FORWARD = {
    "0001-self-compliance-validate": "train:self-compliance:validate-lifecycle",
    "0002-coach-drives-lifecycle": "train:issue-lifecycle:drive-state-machine",
    "0003-author-substrate": "train:substrate:author-artifacts",
    "0004-admit-substrate": "train:substrate:admit-packages",
    "0005-bind-substrate": "train:substrate:bind-runtime",
}


@pytest.mark.parametrize("legacy,typed", sorted(_EXPECTED_FORWARD.items()))
def test_forward_maps_legacy_to_typed(legacy: str, typed: str) -> None:
    assert mig.forward(legacy) == typed


@pytest.mark.parametrize("typed", sorted(_EXPECTED_FORWARD.values()))
def test_forward_results_are_valid_typed_urns(typed: str) -> None:
    assert URNGrammar.validate_grammar(typed) is True
    parsed = URNGrammar.parse_urn(typed)
    assert parsed["type"] == "train"
    assert parsed["subject"] and parsed["slug"]


@pytest.mark.parametrize("legacy", sorted(_EXPECTED_FORWARD))
def test_forward_then_rollback_is_identity(legacy: str) -> None:
    assert mig.rollback(mig.forward(legacy)) == legacy


def test_rollback_is_a_true_inverse_of_the_whole_map() -> None:
    fwd = mig.build_alias_map()
    inv = mig.build_inverse_map()
    assert len(inv) == len(fwd), "inverse must be 1:1 (no two legacy ids collide to one typed urn)"
    for legacy, typed in fwd.items():
        assert inv[typed] == legacy


def test_every_present_legacy_train_is_covered() -> None:
    """No legacy train file in plan/_trains/ is left without an alias."""
    present = {
        p.stem
        for p in _TRAINS_DIR.glob("*.yaml")
        if not p.name.startswith("_")
    }
    missing = present - set(mig.LEGACY_TRAIN_ALIASES)
    assert missing == set(), f"legacy trains missing an alias: {sorted(missing)}"


def test_on_disk_alias_file_agrees_with_constant() -> None:
    """C2's resolver reads plan/_trains/_aliases.yaml; it must match the tool."""
    path = _TRAINS_DIR / "_aliases.yaml"
    assert path.exists(), "alias map data file must exist for the resolver"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    aliases = raw.get("aliases") or {}
    for legacy, typed in _EXPECTED_FORWARD.items():
        subject, slug = typed[len("train:"):].split(":", 1)
        assert legacy in aliases, f"{legacy} absent from _aliases.yaml"
        # Accept subject/slug or subject:slug or train:subject:slug forms.
        assert mig.parse_alias_value(aliases[legacy]) == (subject, slug)


def test_relocation_plan_moves_flat_to_nested(tmp_path: Path) -> None:
    """The (run-last) relocation plan maps each flat file to its nested home,
    without touching disk when only planning."""
    plan = tmp_path / "plan" / "_trains"
    plan.mkdir(parents=True)
    (plan / "0003-author-substrate.yaml").write_text("train_id: 0003-author-substrate\n", encoding="utf-8")
    moves = mig.plan_relocations(tmp_path)
    assert (plan / "0003-author-substrate.yaml", plan / "substrate" / "author-artifacts.yaml") in moves
    # planning is side-effect free
    assert (plan / "0003-author-substrate.yaml").exists()
    assert not (plan / "substrate").exists()
