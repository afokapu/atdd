# URN: test:author-plan-substrate:author-contract:E008-UNIT-001-derives-path-id-and-registers
# Acceptance: acc:author-plan-substrate:E008-UNIT-001-derives-path-id-and-registers
# WMBT: wmbt:author-plan-substrate:E008
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E008-UNIT-001 (plan contract) — create_contract derives the path from the
identity, sets $id to contract:{identity}, writes a schema-valid file, and
dedup-inserts a sorted entry into contracts/_contracts.yaml.

RED until create_contract exists (the keystone writer, #1314 B).
"""
from __future__ import annotations

import json

import yaml

from atdd.planner.commands.author import create_contract


def test_create_contract_derives_path_sets_id_and_registers(tmp_path):
    spec = {
        "identity": "commons:compliance:probe",
        "title": "CommonsComplianceProbe",
        "description": "a probe contract",
        "version": "1.0.0",
        "producers": ["wagon:govern-lifecycle"],
        "consumers": ["wagon:observe-and-correct"],
    }
    path = create_contract(spec, root=tmp_path)

    # Path derived from the theme-first identity: theme/category are dirs, aspect is the file.
    assert path == tmp_path / "contracts" / "commons" / "compliance" / "probe.schema.json"
    assert path.exists()

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["$id"] == "contract:commons:compliance:probe"
    assert doc["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert doc["title"] == "CommonsComplianceProbe"
    assert doc["version"] == "1.0.0"

    # Registry shape matches the #1332 (D) coherence validator:
    # {identity, path, theme, producers, consumers, external?}, identity bare.
    registry = yaml.safe_load((tmp_path / "contracts" / "_contracts.yaml").read_text())
    entries = registry["contracts"]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["identity"] == "commons:compliance:probe"
    assert entry["theme"] == "commons"
    assert entry["path"] == "contracts/commons/compliance/probe.schema.json"
    assert entry["producers"] == ["wagon:govern-lifecycle"]
    assert entry["consumers"] == ["wagon:observe-and-correct"]
    assert "contract:" not in entry["identity"]


def test_create_contract_dedup_insert_is_idempotent_and_sorted(tmp_path):
    a = {"identity": "commons:sensory:gesture", "title": "Gesture"}
    b = {"identity": "commons:compliance:probe", "title": "Probe"}
    create_contract(a, root=tmp_path)
    create_contract(b, root=tmp_path)
    create_contract(dict(a), root=tmp_path)  # re-insert → dedup, no growth

    registry = yaml.safe_load((tmp_path / "contracts" / "_contracts.yaml").read_text())
    ids = [e["identity"] for e in registry["contracts"]]
    assert ids == ["commons:compliance:probe", "commons:sensory:gesture"]  # deduped + sorted
