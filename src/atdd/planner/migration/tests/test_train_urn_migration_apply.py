# Component: component:atdd-plan-core:migration:TrainUrnMigration:backend:tests
# Purpose: destructive apply()/revert() of the train-URN migration (#1421 Layer 7).
"""RED/GREEN for the DESTRUCTIVE half of the train-URN migration (#1421).

The alias-map/rollback half is pinned by ``test_train_urn_migration.py``. This
module pins the run-last relocation that actually rewrites ``plan/``:

* ``apply(root)`` relocates every flat ``NNNN-slug`` train to its typed nested
  home ``plan/_trains/<subject>/<slug>.yaml``, retypes ``train_id`` to the typed
  URN, and records ``category`` as a FIELD (retiring the identity digit);
* each migrated train file still validates against ``train.schema.json`` (which
  accepts the typed id and the ``category`` enum);
* the rewritten ``plan/_trains.yaml`` round-trips through the readers — every
  entry's ``path`` points at the on-disk file, ``wagons`` is preserved, and
  ``TrainResolver`` resolves BOTH the typed URN and the legacy alias to the same
  nested file;
* ``apply`` is idempotent (a second run is a no-op); and
* ``revert(root)`` is a true inverse — flat files + legacy ids restored, nested
  homes gone.

Every test runs on a hermetic COPY of the real ``plan/_trains`` tree (apply is
destructive), so the repo is never mutated by the suite.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.graph.resolver import TrainResolver
from atdd.coach.utils.graph.urn import URNGrammar
from atdd.planner.migration import train_urn_migration as mig

_REPO_ROOT = Path(__file__).resolve().parents[5]
_REAL_TRAINS_DIR = _REPO_ROOT / "plan" / "_trains"
_REAL_REGISTRY = _REPO_ROOT / "plan" / "_trains.yaml"
_SCHEMA_PATH = _REPO_ROOT / "src" / "atdd" / "planner" / "schemas" / "train.schema.json"

_EXPECTED_FORWARD = {
    "0001-self-compliance-validate": ("self-compliance", "validate-lifecycle"),
    "0002-coach-drives-lifecycle": ("issue-lifecycle", "drive-state-machine"),
    "0003-author-substrate": ("substrate", "author-artifacts"),
    "0004-admit-substrate": ("substrate", "admit-packages"),
    "0005-bind-substrate": ("substrate", "bind-runtime"),
}


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A hermetic repo root holding a PRE-migration copy of the real train tree.

    Copies the real tree, then normalizes it to the legacy flat shape via the
    module's own (tested) ``revert`` so the fixture is deterministic REGARDLESS
    of whether the live ``plan/_trains`` has already been migrated — the apply
    tests always start from a known pre-migration baseline.
    """
    dst_trains = tmp_path / "plan" / "_trains"
    shutil.copytree(_REAL_TRAINS_DIR, dst_trains)
    shutil.copy2(_REAL_REGISTRY, tmp_path / "plan" / "_trains.yaml")
    mig.revert(tmp_path)  # normalize to flat NNNN-slug baseline (no-op if already flat)
    # The resolver's legacy dual-resolution consults the projected alias file.
    mig.write_alias_file(tmp_path)
    return tmp_path


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _validate_migrated_fields(doc: dict) -> None:
    """Validate exactly the fields the migration governs — the typed ``train_id``
    and the ``category`` FIELD — against the train schema's own subschemas.

    (Whole-document validation is deliberately NOT asserted: several real train
    files carry pre-existing, migration-unrelated violations, e.g. a 3-segment
    ``sequence[].artifact`` the schema's 2-segment pattern rejects. #1421 only
    retypes the identity + adds the category field.)
    """
    import jsonschema

    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(instance=doc["train_id"], schema=schema["properties"]["train_id"])
    jsonschema.validate(instance=doc["category"], schema=schema["properties"]["category"])


def test_apply_relocates_every_flat_train_to_its_typed_home(repo: Path) -> None:
    mig.apply(repo)
    trains_dir = repo / "plan" / "_trains"
    for legacy_id, (subject, slug) in _EXPECTED_FORWARD.items():
        assert not (trains_dir / f"{legacy_id}.yaml").exists(), (
            f"flat legacy file for {legacy_id} must be gone after apply"
        )
        nested = trains_dir / subject / f"{slug}.yaml"
        assert nested.exists(), f"typed nested home missing: {nested}"


def test_migrated_files_are_typed_and_carry_category_field(repo: Path) -> None:
    mig.apply(repo)
    trains_dir = repo / "plan" / "_trains"
    for legacy_id, (subject, slug) in _EXPECTED_FORWARD.items():
        doc = _load(trains_dir / subject / f"{slug}.yaml")
        assert doc["train_id"] == f"train:{subject}:{slug}"
        assert doc.get("category") == "nominal"
        assert "category_digit" not in doc, "identity digit must be retired"


def test_migrated_files_validate_against_typed_schema(repo: Path) -> None:
    mig.apply(repo)
    trains_dir = repo / "plan" / "_trains"
    for subject, slug in _EXPECTED_FORWARD.values():
        _validate_migrated_fields(_load(trains_dir / subject / f"{slug}.yaml"))


def test_registry_entries_point_at_real_files_and_preserve_wagons(repo: Path) -> None:
    before = mig._flatten_registry(_load(repo / "plan" / "_trains.yaml").get("trains", {}))
    wagons_before = {
        mig.forward(legacy): before[legacy].get("wagons", [])
        for legacy in _EXPECTED_FORWARD
    }

    mig.apply(repo)

    after = mig._flatten_registry(_load(repo / "plan" / "_trains.yaml").get("trains", {}))
    assert set(after) == {mig.forward(k) for k in _EXPECTED_FORWARD}
    for typed, entry in after.items():
        assert entry["train_id"] == typed
        assert entry.get("category") == "nominal"
        path = repo / entry["path"]
        assert path.exists(), f"registry path does not exist: {path}"
        assert _load(path)["train_id"] == typed
        # wagons carried forward verbatim (issue_graph reads them for ordering)
        assert entry.get("wagons", []) == wagons_before[typed]


def test_resolver_resolves_both_typed_and_legacy_alias(repo: Path) -> None:
    mig.apply(repo)
    resolver = TrainResolver(repo_root=repo)
    for legacy_id, (subject, slug) in _EXPECTED_FORWARD.items():
        typed_urn = f"train:{subject}:{slug}"
        nested = repo / "plan" / "_trains" / subject / f"{slug}.yaml"

        typed_res = resolver.resolve(typed_urn)
        assert typed_res.is_resolved, f"typed URN broke: {typed_urn} ({typed_res.error})"
        assert typed_res.resolved_paths == [nested]

        legacy_res = resolver.resolve(f"train:{legacy_id}")
        assert legacy_res.is_resolved, (
            f"legacy alias broke post-migration: {legacy_id} ({legacy_res.error})"
        )
        assert legacy_res.resolved_paths == [nested]


def test_apply_is_idempotent(repo: Path) -> None:
    first = mig.apply(repo)
    registry_after_first = _load(repo / "plan" / "_trains.yaml")
    second = mig.apply(repo)
    assert _load(repo / "plan" / "_trains.yaml") == registry_after_first
    assert {t for t, *_ in first} == {t for t, *_ in second}


def test_revert_is_a_true_inverse(repo: Path) -> None:
    trains_dir = repo / "plan" / "_trains"
    mig.apply(repo)
    mig.revert(repo)

    for legacy_id, (subject, slug) in _EXPECTED_FORWARD.items():
        flat = trains_dir / f"{legacy_id}.yaml"
        assert flat.exists(), f"revert must restore flat file {flat}"
        assert _load(flat)["train_id"] == legacy_id
        assert "category" not in _load(flat)
        assert not (trains_dir / subject / f"{slug}.yaml").exists()

    # registry back to a legacy-shaped, reader-valid state
    restored = mig._flatten_registry(_load(repo / "plan" / "_trains.yaml").get("trains", {}))
    assert set(restored) == set(_EXPECTED_FORWARD)
