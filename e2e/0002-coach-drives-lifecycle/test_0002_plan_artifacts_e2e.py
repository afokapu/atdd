# URN: test:train:0002-coach-drives-lifecycle:E2E-001-plan-artifacts
# Train: train:0002-coach-drives-lifecycle
# Phase: GREEN
# Layer: assembly
# Runtime: python
# Purpose: E2E for the coach v9 bootstrap validation slice — the plan artifacts
#          authored in this slice must parse, register, and resolve coherently.
#          Track-Q1 will replace this with a real coach-driven cycle once the
#          implementation lands.
"""
End-to-end test for train:0002-coach-drives-lifecycle plan artifacts.

This is the validation-slice E2E. It exercises the plan-artifact graph that
the coach v9 bootstrap PR lands:

- Train 0002 is registered in plan/_trains.yaml and parses via the train YAML
  shape (matching 0001).
- Wagon freeze-runtime-contracts is registered in plan/_wagons.yaml and its
  manifest at plan/freeze_runtime_contracts/_freeze_runtime_contracts.yaml is
  shaped per the wagon convention.
- The wagon's feature (runtime-schema-freeze) is registered in the manifest
  and its YAML lists the four WMBT URNs that exist as files alongside.
- Each WMBT URN has a corresponding YAML in the wagon directory.

Q1 will supersede this test with an actual coach-driven cycle once the
implementation tracks (J/K/L/M/N/O/P) merge.
"""

import yaml
from pathlib import Path

from atdd.coach.utils.repo import find_repo_root


REPO_ROOT = find_repo_root()


class TestStep1TrainRegistration:
    """Train 0002 is registered and parses."""

    def test_train_yaml_exists_and_parses(self):
        train_file = REPO_ROOT / "plan" / "_trains" / "0002-coach-drives-lifecycle.yaml"
        assert train_file.exists(), f"Missing: {train_file}"
        data = yaml.safe_load(train_file.read_text())
        assert data["train_id"] == "0002-coach-drives-lifecycle"
        assert data["primary_wagon"] == "freeze-runtime-contracts"
        assert "wagon:freeze-runtime-contracts" in data["participants"]

    def test_train_registered_in_trains_yaml(self):
        trains_file = REPO_ROOT / "plan" / "_trains.yaml"
        data = yaml.safe_load(trains_file.read_text())
        commons = data["trains"]["0-commons"]["00-commons-nominal"]
        train_ids = {t["train_id"] for t in commons}
        assert "0002-coach-drives-lifecycle" in train_ids


class TestStep2WagonRegistration:
    """Coach v9 wagons are registered in plan/_wagons.yaml."""

    def test_nine_coach_v9_wagons_registered(self):
        wagons_file = REPO_ROOT / "plan" / "_wagons.yaml"
        data = yaml.safe_load(wagons_file.read_text())
        wagon_names = {w["wagon"] for w in data["wagons"]}
        expected = {
            "freeze-runtime-contracts",
            "drive-state-machine",
            "spawn-agents",
            "observe-and-correct",
            "dispatch-validators",
            "review-phase-boundaries",
            "judge-ambiguous-decisions",
            "discover-and-decommission",
            "integrate-end-to-end",
        }
        assert expected <= wagon_names, f"Missing: {expected - wagon_names}"

    def test_freeze_runtime_contracts_manifest_parses(self):
        manifest = (
            REPO_ROOT
            / "plan"
            / "freeze_runtime_contracts"
            / "_freeze_runtime_contracts.yaml"
        )
        assert manifest.exists()
        data = yaml.safe_load(manifest.read_text())
        assert data["wagon"] == "freeze-runtime-contracts"
        assert data["urn"] == "wagon:freeze-runtime-contracts"
        assert data["subject"] == "agent:coach"
        assert data["consume"] == []  # contract-freeze entry point
        produce_names = {p["name"] for p in data["produce"]}
        assert "commons:coach:runtime-event-schema" in produce_names
        assert "commons:coach:event-semantics-doc" in produce_names


class TestStep3FeatureAndWMBTs:
    """The runtime-schema-freeze feature lists 4 WMBTs that exist as YAML."""

    def test_feature_yaml_parses(self):
        feature = (
            REPO_ROOT
            / "plan"
            / "freeze_runtime_contracts"
            / "features"
            / "runtime_schema_freeze.yaml"
        )
        assert feature.exists()
        data = yaml.safe_load(feature.read_text())
        assert data["urn"] == "feature:freeze-runtime-contracts:runtime-schema-freeze"
        assert data["sizing"]["wmbts"] == 4

    def test_four_wmbt_files_exist_and_match_feature(self):
        feature = (
            REPO_ROOT
            / "plan"
            / "freeze_runtime_contracts"
            / "features"
            / "runtime_schema_freeze.yaml"
        )
        wmbts_in_feature = yaml.safe_load(feature.read_text())["wmbts"]
        wagon_dir = REPO_ROOT / "plan" / "freeze_runtime_contracts"

        for urn in wmbts_in_feature:
            step_id = urn.split(":")[-1]  # e.g. "D001"
            wmbt_file = wagon_dir / f"{step_id}.yaml"
            assert wmbt_file.exists(), f"Missing WMBT YAML: {wmbt_file}"
            wmbt = yaml.safe_load(wmbt_file.read_text())
            assert wmbt["urn"] == urn
            assert wmbt["acceptances"], f"{urn} has no acceptances"


class TestStep4AcceptanceURNs:
    """Acceptance URNs referenced by the C0 issue body resolve to acceptances."""

    def test_d001_six_schemas_exist_acceptance(self):
        wmbt = yaml.safe_load(
            (REPO_ROOT / "plan" / "freeze_runtime_contracts" / "D001.yaml").read_text()
        )
        urns = {a["identity"]["urn"] for a in wmbt["acceptances"]}
        assert "acc:freeze-runtime-contracts:D001-UNIT-001-six-schemas-exist" in urns

    def test_all_four_wmbts_have_at_least_one_acceptance(self):
        wagon_dir = REPO_ROOT / "plan" / "freeze_runtime_contracts"
        for step in ("D001", "D002", "D003", "D004"):
            wmbt = yaml.safe_load((wagon_dir / f"{step}.yaml").read_text())
            assert len(wmbt["acceptances"]) >= 1, f"{step} missing acceptances"
