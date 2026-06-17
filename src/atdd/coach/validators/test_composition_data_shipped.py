# Phase: SMOKE
# Layer: integration
"""Guard (#1132): the package-data globs must ship the data the package-composition CLI
reads — the core convention nodes (coach + planner `nodes/`) and the convention-node
schema (`planner/schemas/author/`). Without them a pip-installed toolkit resolves zero
core nodes and `atdd validate package` wrongly fails, breaking atdd-extensions CI. This
guards against a silent package-data regression."""
from __future__ import annotations

import pathlib
import tomllib

from atdd.planner.commands import compose as C

_REPO = pathlib.Path(__file__).resolve().parents[4]


def _package_data() -> dict:
    data = tomllib.loads((_REPO / "pyproject.toml").read_text())
    return data["tool"]["setuptools"]["package-data"]


def test_package_data_ships_core_nodes_and_schema():
    pd = _package_data()
    assert "nodes/*.yaml" in pd.get("atdd.coach.conventions", []), "coach nodes/ not shipped"
    assert "nodes/*.yaml" in pd.get("atdd.planner.conventions", []), "planner nodes/ not shipped"
    assert "author/*.json" in pd.get("atdd.planner.schemas", []), "convention-node schema not shipped"


def test_installed_core_node_ids_resolves_package_relative():
    # the CLI's core authority loads from Path(atdd.__file__).parent — must be non-empty
    ids = C.installed_core_node_ids()
    assert len(ids) >= 30, f"expected the core node set, resolved {len(ids)}"
    assert any(i.startswith("coach.") for i in ids)
    assert any(i.startswith("planner.") for i in ids)
