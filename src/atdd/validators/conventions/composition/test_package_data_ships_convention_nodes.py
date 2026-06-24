# URN: test:validate-conventions:composition-variants:package_data_ships_convention_nodes
# WMBT: wmbt:validate-conventions:E010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `composition/package_data_ships_convention_nodes` (#1206).

Instantiates the `composition/composed_graph_loads` template against the composed convention
graph. Traversal execution lands incrementally on the _support graph engine;
this module fixes the variant's contract + legacy parity binding and is runnable
in parallel with legacy validators (imports no persona validator module).
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
from pathlib import Path

from atdd.validators.conventions._support.graph_loader import load_composed_graph
from atdd.validators.conventions.composition.archetype import TEMPLATE_IDS, TEMPLATES

FAMILY = "composition"
TEMPLATE = "composed_graph_loads"
VARIANT = "package_data_ships_convention_nodes"
QUESTION = 'Can all convention sources be loaded into one composed graph?'
SELECTOR = 'all convention source files/packages'
TRAVERSAL = 'source files -> parse -> local graph fragments -> composed graph'
INVARIANT = 'graph construction succeeds with no parse/load errors'
AUTO_CAPTURE = 'a new node is included if it lives in a convention source path included by the graph loader'
FAILURE_EVIDENCE = ['source_file', 'parse_error', 'node_id_if_available', 'package_id']
LEGACY_PARITY_SOURCES = ['src/atdd/coach/validators/test_composition_data_shipped.py']


_REPO_ROOT = Path(__file__).resolve().parents[5]
_CONFIG = {"variant": VARIANT}
# Legacy nodeid whose green-on-clean / red-on-fault we measure for parity.
_LEGACY_NODEID = (
    "src/atdd/coach/validators/test_composition_data_shipped.py"
    "::test_package_data_ships_core_nodes_and_schema"
)
# The exact package-data glob fragment the fault removes (first occurrence is the
# coach.conventions nodes glob; must be present on the clean repo).
_FAULT_GLOB = ', "nodes/*.yaml"'


def _template():
    by_id = {t.template_id: t for t in TEMPLATES}
    return by_id[TEMPLATE]


def _convention_evidence(repo_root: Path):
    """Run the variant through the OFFICIAL path: real composed graph ->
    TemplateContract.evaluate(graph, config)."""
    return _template().evaluate(load_composed_graph(repo_root), config=_CONFIG)


def _legacy_caught(repo_root: Path) -> bool:
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", _LEGACY_NODEID, "-q", "-p", "no:cacheprovider"],
        cwd=repo_root, env={"PYTHONPATH": "src", "PATH": os.environ["PATH"]},
        capture_output=True, text=True,
    ).returncode
    return rc != 0


@contextlib.contextmanager
def _drop_package_data_glob(repo_root: Path):
    """Inject the variant's fault into a temp-restored copy of the real
    pyproject.toml: drop a convention-node package-data glob, then revert."""
    p = repo_root / "pyproject.toml"
    orig = p.read_text(encoding="utf-8")
    assert _FAULT_GLOB in orig, "fault precondition: package-data glob must exist on clean repo"
    p.write_text(orig.replace(_FAULT_GLOB, "", 1), encoding="utf-8")
    try:
        yield
    finally:
        p.write_text(orig, encoding="utf-8")


def test_package_data_ships_convention_nodes_variant_contract() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{TEMPLATE} not in composition archetype"
    assert LEGACY_PARITY_SOURCES, "variant must record >=1 legacy parity source"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"


def test_clean_baseline_no_violations() -> None:
    # The real repo ships every required convention-node/schema glob.
    assert _convention_evidence(_REPO_ROOT) == []


def test_evidence_keys_subset_of_failure_evidence() -> None:
    # On an injected fault the evidence keys must be a SUBSET of the contract.
    allowed = set(FAILURE_EVIDENCE)
    with _drop_package_data_glob(_REPO_ROOT):
        ev = _convention_evidence(_REPO_ROOT)
    assert ev, "convention path must flag the dropped glob"
    for record in ev:
        assert set(record).issubset(allowed), f"evidence keys escape contract: {set(record) - allowed}"


def test_fault_injection_legacy_parity() -> None:
    # BOTH suites must be silent on the clean repo, then BOTH must catch the
    # injected fault (dropped convention-node package-data glob). Real parity.
    assert _convention_evidence(_REPO_ROOT) == [], "convention path must be clean on clean repo"
    assert not _legacy_caught(_REPO_ROOT), "legacy must be green on clean repo"
    with _drop_package_data_glob(_REPO_ROOT):
        convention_caught = bool(_convention_evidence(_REPO_ROOT))
        legacy_caught = _legacy_caught(_REPO_ROOT)
    assert convention_caught and legacy_caught, (
        f"parity failure: convention_caught={convention_caught} legacy_caught={legacy_caught}"
    )
