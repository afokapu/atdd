# URN: test:validate-conventions:variant-metadata-conformance:E011-RED-001-behavioral-shadow
# Acceptance: acc:validate-conventions:E011-SMOKE-001-seed
# WMBT: wmbt:validate-conventions:E011
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""#1206 behavioral shadow harness — RED until the _support graph engine and
executable archetypes land.

These tests assert BEHAVIORAL parity, not metadata scaffolding. They fail today
because:
  - `_support/graph_loader.load_composed_graph` is not implemented,
  - `archetype.TEMPLATES[*]` expose metadata but no `evaluate(graph)`,
  - per-family `fixtures.py` carry no VALID/INVALID fragments.

Driven by `legacy-validator-map.yaml` (not 237 hand-written tests). The #1206
graph-traversal engine must make every check below pass before behavioral parity
can be claimed or any legacy validator decommissioned.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import yaml


def _load_graph(repo_root: Path):
    from atdd.validators.conventions._support.graph_loader import load_composed_graph
    return load_composed_graph(repo_root)


def _templates(family: str) -> dict:
    mod = importlib.import_module(f"atdd.validators.conventions.{family}.archetype")
    return {t.template_id: t for t in mod.TEMPLATES}


def _fixtures(family: str, template: str):
    mod = importlib.import_module(f"atdd.validators.conventions.{family}.fixtures")
    return (getattr(mod, "VALID_FRAGMENTS", {}).get(template, {}),
            getattr(mod, "INVALID_FRAGMENTS", {}).get(template, {}))


def _p0_pairs(repo_root: Path) -> list:
    m = yaml.safe_load((repo_root / "docs" / "validator-parity"
                        / "legacy-validator-map.yaml").read_text(encoding="utf-8"))
    return [e for e in m["entries"]
            if e.get("priority") == "P0"
            and e.get("parity_status") in {"direct", "split", "merged"}]


def test_composed_convention_graph_loads(repo_root: Path) -> None:
    g = _load_graph(repo_root)
    assert getattr(g, "nodes", None) is not None, "composed graph has no nodes"


def test_known_good_fixture_passes(repo_root: Path) -> None:
    checked = 0
    for e in _p0_pairs(repo_root):
        fam, tmpl = e["proposed_family"], e["proposed_template"]
        valid, _ = _fixtures(fam, tmpl)
        tc = _templates(fam)[tmpl]
        for name, fragment in valid.items():
            violations = tc.evaluate(fragment)  # engine API
            assert not violations, f"{fam}/{tmpl}: known-good {name} flagged {violations}"
            checked += 1
    assert checked, "no known-good fixtures exercised"


def test_known_bad_fixture_fails(repo_root: Path) -> None:
    checked = 0
    for e in _p0_pairs(repo_root):
        fam, tmpl = e["proposed_family"], e["proposed_template"]
        _, invalid = _fixtures(fam, tmpl)
        tc = _templates(fam)[tmpl]
        for name, fragment in invalid.items():
            violations = tc.evaluate(fragment)
            assert violations, f"{fam}/{tmpl}: known-bad {name} not caught"
            checked += 1
    assert checked, "no known-bad fixtures exercised"


def test_variant_emits_template_shaped_evidence(repo_root: Path) -> None:
    for e in _p0_pairs(repo_root):
        fam, tmpl = e["proposed_family"], e["proposed_template"]
        _, invalid = _fixtures(fam, tmpl)
        tc = _templates(fam)[tmpl]
        allowed = set(tc.failure_evidence)
        for name, fragment in invalid.items():
            for ev in tc.evaluate(fragment):
                assert set(ev).issubset(allowed), (
                    f"{fam}/{tmpl}: evidence {set(ev)} not template-shaped ⊆ {allowed}"
                )


def test_p0_target_catches_legacy_failure_class(repo_root: Path) -> None:
    """Shadow: each P0 target variant must catch its legacy counterpart's bad case."""
    graph = _load_graph(repo_root)
    gaps = []
    for e in _p0_pairs(repo_root):
        fam, tmpl = e["proposed_family"], e["proposed_template"]
        _, invalid = _fixtures(fam, tmpl)
        tc = _templates(fam)[tmpl]
        if not invalid or not any(tc.evaluate(f) for f in invalid.values()):
            gaps.append(f"{e['legacy_path']} -> {e['proposed_target_path']}")
    assert not gaps, ("P0 behavioral parity gaps (target does not catch legacy "
                      f"failure class):\n" + "\n".join(gaps))
