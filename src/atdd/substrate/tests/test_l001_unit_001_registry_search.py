# URN: test:admit-substrate:substrate-admission:L001-UNIT-001-registry-search
# Acceptance: acc:admit-substrate:L001-UNIT-001-registry-search
# WMBT: wmbt:admit-substrate:L001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""L001-UNIT-001 — search matches by alias, canonical id, tag, and --kind filter,
returns candidate fields, and returns empty (installs nothing) on no match."""
from __future__ import annotations

import pathlib

from atdd.substrate import registry

INDEX = pathlib.Path(__file__).parent / "fixtures" / "registry" / "index.yaml"


def _entries():
    return registry.load_registry_index(INDEX)


def test_search_by_alias() -> None:
    res = registry.search(_entries(), "demo")
    assert [e.id for e in res] == ["acme.extension.demo"]


def test_search_by_id_substring() -> None:
    res = registry.search(_entries(), "alpha")
    assert [e.id for e in res] == ["acme.extension.alpha"]


def test_search_by_tag() -> None:
    res = registry.search(_entries(), "pytest")  # tag unique to the workspace entry
    assert [e.id for e in res] == ["acme.workspace.runtime"]


def test_kind_filter_restricts() -> None:
    res = registry.search(_entries(), "", kind="workspace")  # empty query matches all of kind
    assert all(e.kind == "workspace" for e in res)
    assert "acme.workspace.runtime" in [e.id for e in res]
    assert "acme.extension.demo" not in [e.id for e in res]


def test_result_fields_present() -> None:
    e = registry.search(_entries(), "demo")[0]
    assert e.kind == "extension"
    assert e.latest_version == "0.1.0"
    assert e.trust == "community"


def test_no_match_returns_empty() -> None:
    assert registry.search(_entries(), "nonexistent-xyz") == []
